"""A stateless USSD menu session that produces a structured report draft.

Why USSD is worth building alongside SMS: a menu *structurally* yields the
report type, headcount, and need tag, instead of hoping keyword matching finds
them in free text. Roadmap §5.3 makes exactly this point — structure is what
lets responders and the AI layer act on a report rather than merely read it.

The session carries no server-side state. Aggregators accumulate every keypress
into one ``*``-delimited ``text`` field and resend the whole thing on each step,
so the number of segments *is* the step counter. That keeps the gateway
horizontally scalable and immune to session-store expiry, which matters when
the network it runs on is already degraded.

Responses follow the USSD convention of a plain-text body prefixed with
``CON `` to keep the session open or ``END `` to close it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gateway_identity import ReportDraft
from .models import Language, ReportType

_MAX_PEOPLE_COUNT = 100_000

# SAFE_ROUTE is deliberately absent: it is a request for information rather
# than a report of an incident, and a USSD session has no route data to answer
# with. INSTRUCTION is responder-only and never sender-originated.
_TYPE_CHOICES: tuple[tuple[ReportType, str, str], ...] = (
    ("SOS", "Urgent help", "জরুরি সাহায্য"),
    ("MEDICAL_NEED", "Medical help", "চিকিৎসা সহায়তা"),
    ("RESOURCE_NEED", "Food/water", "ত্রাণ সামগ্রী"),
    ("SHELTER_INFO", "Shelter info", "আশ্রয়কেন্দ্র তথ্য"),
    ("HAZARD_UPDATE", "Hazard report", "বিপদ সংকেত"),
    ("SAFETY_STATUS", "I am safe", "আমি নিরাপদ"),
)

_NEED_CHOICES: tuple[tuple[str | None, str, str], ...] = (
    ("water", "Water", "পানি"),
    ("food", "Food", "খাবার"),
    ("medical", "Medical", "চিকিৎসা"),
    ("rescue", "Rescue", "উদ্ধার"),
    ("shelter", "Shelter", "আশ্রয়"),
    (None, "Something else", "অন্য কিছু"),
)

_PROMPTS: dict[str, dict[Language, str]] = {
    "language": {"en": "Protidhoni crisis line\n1. English\n2. বাংলা", "bn": ""},
    "type": {
        "en": "What are you reporting?",
        "bn": "আপনি কী জানাতে চান?",
    },
    "people": {
        "en": "How many people are affected?\nEnter a number, or 0 if unknown.",
        "bn": "কতজন ক্ষতিগ্রস্ত?\nসংখ্যা লিখুন, জানা না থাকলে ০।",
    },
    "need": {
        "en": "What is most needed?",
        "bn": "সবচেয়ে বেশি কী প্রয়োজন?",
    },
    "submitted": {
        "en": "Report received. Responders can now see it. Stay safe.",
        "bn": "রিপোর্ট গৃহীত হয়েছে। উদ্ধারকর্মীরা এটি দেখতে পাবেন। নিরাপদে থাকুন।",
    },
    "invalid": {
        "en": "Sorry, that was not a valid choice. Please dial again.",
        "bn": "দুঃখিত, এটি সঠিক নির্বাচন নয়। আবার ডায়াল করুন।",
    },
}

_SUMMARY_LABELS: dict[Language, tuple[str, str, str]] = {
    "en": ("USSD report", "People affected", "Most needed"),
    "bn": ("ইউএসএসডি রিপোর্ট", "ক্ষতিগ্রস্ত", "প্রয়োজন"),
}

_UNKNOWN: dict[Language, str] = {"en": "not stated", "bn": "জানানো হয়নি"}


@dataclass(frozen=True)
class UssdResponse:
    """One USSD turn. ``draft`` is set only on the turn that completes a report."""

    body: str
    draft: ReportDraft | None = None

    @property
    def is_final(self) -> bool:
        return self.body.startswith("END ")


def _con(text: str) -> UssdResponse:
    return UssdResponse(body=f"CON {text}")


def _end(text: str, *, draft: ReportDraft | None = None) -> UssdResponse:
    return UssdResponse(body=f"END {text}", draft=draft)


def _menu(prompt: str, labels: list[str]) -> str:
    numbered = "\n".join(f"{index}. {label}" for index, label in enumerate(labels, start=1))
    return f"{prompt}\n{numbered}"


def _parse_choice(raw: str, option_count: int) -> int | None:
    """Return a zero-based menu index, or None when the keypress was not valid."""
    if not raw.isdigit():
        return None
    choice = int(raw)
    if not 1 <= choice <= option_count:
        return None
    return choice - 1


def _build_summary(
    language: Language,
    report_type: ReportType,
    people_count: int | None,
    need: str | None,
) -> str:
    """Render the menu selections as the report's human-readable text.

    The schema requires a non-empty ``payload.text``, and a responder reading
    the dashboard should see a sentence rather than raw menu codes.
    """
    heading, people_label, need_label = _SUMMARY_LABELS[language]
    type_label = next(
        (en if language == "en" else bn) for value, en, bn in _TYPE_CHOICES if value == report_type
    )
    need_text = _UNKNOWN[language]
    if need is not None:
        need_text = next(
            (en if language == "en" else bn) for value, en, bn in _NEED_CHOICES if value == need
        )
    people_text = _UNKNOWN[language] if people_count is None else str(people_count)
    # Bangla sentences terminate with a danda, not a full stop.
    stop = "।" if language == "bn" else "."
    return (
        f"{heading}: {type_label}{stop} "
        f"{people_label}: {people_text}{stop} "
        f"{need_label}: {need_text}{stop}"
    )


def advance_session(text: str) -> UssdResponse:
    """Advance one USSD turn from the aggregator's accumulated input string.

    ``text`` is empty on the first turn and gains one ``*``-delimited segment
    per keypress, so its segment count is the number of answers received.
    """
    segments = [segment.strip() for segment in text.split("*")] if text.strip() else []

    if not segments:
        return _con(_PROMPTS["language"]["en"])

    language_choice = _parse_choice(segments[0], 2)
    if language_choice is None:
        return _end(_PROMPTS["invalid"]["en"])
    language: Language = "en" if language_choice == 0 else "bn"

    if len(segments) == 1:
        labels = [(en if language == "en" else bn) for _, en, bn in _TYPE_CHOICES]
        return _con(_menu(_PROMPTS["type"][language], labels))

    type_choice = _parse_choice(segments[1], len(_TYPE_CHOICES))
    if type_choice is None:
        return _end(_PROMPTS["invalid"][language])
    report_type = _TYPE_CHOICES[type_choice][0]

    if len(segments) == 2:
        return _con(_PROMPTS["people"][language])

    raw_people = segments[2]
    if not raw_people.isdigit():
        return _end(_PROMPTS["invalid"][language])
    parsed_people = int(raw_people)
    # 0 is the documented "unknown" answer, and the schema's minimum is 1.
    people_count = parsed_people if 1 <= parsed_people <= _MAX_PEOPLE_COUNT else None

    if len(segments) == 3:
        labels = [(en if language == "en" else bn) for _, en, bn in _NEED_CHOICES]
        return _con(_menu(_PROMPTS["need"][language], labels))

    need_choice = _parse_choice(segments[3], len(_NEED_CHOICES))
    if need_choice is None:
        return _end(_PROMPTS["invalid"][language])
    need = _NEED_CHOICES[need_choice][0]

    draft = ReportDraft(
        report_type=report_type,
        language=language,
        text=_build_summary(language, report_type, people_count, need),
        people_count=people_count,
        needs=() if need is None else (need,),
    )
    return _end(_PROMPTS["submitted"][language], draft=draft)
