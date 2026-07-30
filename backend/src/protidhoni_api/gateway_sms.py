"""Turn one free-text SMS body into a structured report draft.

Deliberately deterministic keyword matching rather than a call into the AI
service. An SMS arriving during an outage must not fail because the AI
container is down, slow, or unreachable. The gateway produces a valid report
with ``priority: null``; Phase 4 does not claim an automatic enrichment worker.
A rules pass here also stays explainable to a judge, which roadmap §5.4 prefers.

Bangla and English are both matched directly, because the people this path
exists for are the least likely to be writing English.
"""

from __future__ import annotations

import re

from .gateway_identity import GatewayLocation, ReportDraft
from .models import Language, ReportType

MAX_SMS_TEXT_LENGTH = 2000
_MAX_PEOPLE_COUNT = 100_000
_MAX_NEEDS = 20

# Any character in the Bengali Unicode block means the sender wrote Bangla.
_BENGALI_RANGE = re.compile(r"[ঀ-৿]")

# A decimal coordinate pair, e.g. "23.8103,90.4125" or "23.81, 90.41".
_COORDINATE_PATTERN = re.compile(
    r"(?<![\d.])(-?\d{1,2}\.\d{1,8})\s*,\s*(-?\d{1,3}\.\d{1,8})(?![\d.])"
)

# A count only counts when it sits next to a word meaning "people". Matching
# bare integers would happily read a house number or a time as a casualty count.
_PEOPLE_PATTERN = re.compile(
    r"(?:(\d{1,6})\s*(?:people|persons?|person|adults?|children|kids?|জন|ব্যক্তি|মানুষ))"
    r"|(?:(?:people|persons?|person|জন|ব্যক্তি|মানুষ)\s*(\d{1,6}))",
    re.IGNORECASE,
)

# Ordered most-urgent first; ties break toward the earlier entry so a message
# mentioning both bleeding and food is triaged as a medical need, not supplies.
_TYPE_KEYWORDS: tuple[tuple[ReportType, tuple[str, ...]], ...] = (
    (
        "SOS",
        (
            "sos",
            "help",
            "rescue",
            "trapped",
            "drowning",
            "drown",
            "save us",
            "emergency",
            "সাহায্য",
            "উদ্ধার",
            "বাঁচাও",
            "আটকা",
            "ডুবে",
            "জরুরি",
            "বিপদ",
        ),
    ),
    (
        "MEDICAL_NEED",
        (
            "medical",
            "medicine",
            "doctor",
            "injured",
            "injury",
            "bleeding",
            "hospital",
            "ambulance",
            "wounded",
            "fever",
            "ডাক্তার",
            "আহত",
            "রক্ত",
            "ওষুধ",
            "হাসপাতাল",
            "অ্যাম্বুলেন্স",
            "চিকিৎসা",
            "জ্বর",
        ),
    ),
    (
        "HAZARD_UPDATE",
        (
            "flood",
            "flooded",
            "landslide",
            "collapsed",
            "collapse",
            "fire",
            "blocked",
            "bridge",
            "road damaged",
            "cyclone",
            "storm",
            "বন্যা",
            "ধস",
            "ভেঙে",
            "আগুন",
            "বন্ধ",
            "সেতু",
            "ঘূর্ণিঝড়",
            "ঝড়",
            "রাস্তা",
        ),
    ),
    (
        "RESOURCE_NEED",
        (
            "water",
            "food",
            "rice",
            "supplies",
            "drinking",
            "hungry",
            "thirsty",
            "blanket",
            "পানি",
            "খাবার",
            "চাল",
            "ত্রাণ",
            "ক্ষুধা",
            "তৃষ্ণা",
            "কম্বল",
        ),
    ),
    (
        "SHELTER_INFO",
        (
            "shelter",
            "refuge",
            "school building",
            "space available",
            "beds",
            "আশ্রয়",
            "আশ্রয়কেন্দ্র",
            "স্কুলে",
            "থাকার জায়গা",
        ),
    ),
    (
        "SAFETY_STATUS",
        ("safe", "we are ok", "i am ok", "alive", "unharmed", "নিরাপদ", "ভালো আছি", "সুস্থ"),
    ),
)

# Structured need tags. Values stay English so the dashboard and AI clustering
# see one vocabulary regardless of the language the sender wrote in.
_NEED_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("water", ("water", "drinking", "thirsty", "পানি", "তৃষ্ণা")),
    ("food", ("food", "rice", "hungry", "খাবার", "চাল", "ক্ষুধা")),
    (
        "medical",
        (
            "medical",
            "medicine",
            "doctor",
            "injured",
            "bleeding",
            "ambulance",
            "hospital",
            "ডাক্তার",
            "ওষুধ",
            "আহত",
            "রক্ত",
            "হাসপাতাল",
            "চিকিৎসা",
        ),
    ),
    ("rescue", ("rescue", "trapped", "drowning", "stranded", "উদ্ধার", "আটকা", "ডুবে")),
    ("shelter", ("shelter", "refuge", "homeless", "আশ্রয়", "থাকার জায়গা")),
)


class SmsParseError(ValueError):
    """The SMS body carried nothing that could become a report."""


def detect_language(text: str) -> Language:
    return "bn" if _BENGALI_RANGE.search(text) else "en"


def extract_location(text: str) -> tuple[GatewayLocation, str]:
    """Pull an optional 'lat,lng' pair out of the body.

    Returns the location plus the body with the coordinate substring removed,
    so later numeric parsing cannot mistake a longitude for a headcount. The
    schema calls user-typed coordinates ``manual`` — asserted by a person,
    never measured by a device — which is exactly what this is.
    """
    match = _COORDINATE_PATTERN.search(text)
    if match is None:
        return GatewayLocation(), text

    lat, lng = float(match.group(1)), float(match.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return GatewayLocation(), text

    remainder = text[: match.start()] + " " + text[match.end() :]
    return GatewayLocation(lat=lat, lng=lng), remainder


def extract_people_count(text: str) -> int | None:
    match = _PEOPLE_PATTERN.search(text)
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    count = int(raw)
    if not 1 <= count <= _MAX_PEOPLE_COUNT:
        return None
    return count


def infer_report_type(text: str) -> ReportType:
    """Pick the report type with the most keyword hits, most urgent wins ties.

    An unrecognisable message falls back to SOS on purpose: somebody texted a
    crisis line and we could not tell why, which is a reason for a responder to
    look, not a reason to file it as routine. Priority remains null, so this
    default cannot by itself mark the report critical.
    """
    lowered = text.lower()
    best_type: ReportType = "SOS"
    best_score = 0
    for report_type, keywords in _TYPE_KEYWORDS:
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_type, best_score = report_type, score
    return best_type


def extract_needs(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    needs = [
        need for need, keywords in _NEED_KEYWORDS if any(keyword in lowered for keyword in keywords)
    ]
    return tuple(needs[:_MAX_NEEDS])


def parse_sms_body(body: str) -> ReportDraft:
    """Parse one SMS body into a signable draft, or raise SmsParseError."""
    text = body.strip()
    if not text:
        raise SmsParseError("The message body was empty.")
    if len(text) > MAX_SMS_TEXT_LENGTH:
        # Keep the sender's own words rather than rejecting an over-long report:
        # a truncated crisis message still reaches a responder, a dropped one does not.
        text = text[:MAX_SMS_TEXT_LENGTH]

    location, scannable = extract_location(text)
    return ReportDraft(
        report_type=infer_report_type(scannable),
        language=detect_language(text),
        text=text,
        people_count=extract_people_count(scannable),
        needs=extract_needs(scannable),
        location=location,
    )
