"""Small, deterministic Phase 1 crisis-text classifier.

This is an honest fallback, not a disguised use of the pretrained BanglaBERT
probe. It combines a tiny in-repository bilingual TF-IDF model with explicit
urgency and need signals. Phase 2 can replace the type scorer with a validated,
fine-tuned model while preserving the API response contract.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .schemas import ClassificationReport, ClassificationResult, Priority, ReportType

RULE_MODEL_NAME = "phase1-tfidf-rules-v1"
# Kept as a compatibility alias for Phase 1 callers. New application code
# receives an explicit classifier instance from ``build_classifier``.
MODEL_NAME = RULE_MODEL_NAME

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u0980-\u09ff]+", re.IGNORECASE)

_TRAINING_EXAMPLES: dict[ReportType, tuple[str, ...]] = {
    "SOS": (
        "help us urgently people are trapped rescue needed",
        "emergency save us we are drowning",
        "বাঁচান আমরা আটকা পড়েছি জরুরি উদ্ধার দরকার",
    ),
    "MEDICAL_NEED": (
        "injured person needs doctor medicine ambulance",
        "severe bleeding need blood and medical help",
        "আহত রোগীর ডাক্তার ও ওষুধ দরকার রক্তপাত হচ্ছে",
    ),
    "RESOURCE_NEED": (
        "need drinking water food and dry clothes",
        "families need food water and supplies",
        "খাবার বিশুদ্ধ পানি ও ত্রাণ দরকার",
    ),
    "SAFETY_STATUS": (
        "our family is safe everyone is accounted for",
        "person missing unable to contact family",
        "আমরা নিরাপদ আছি একজন নিখোঁজ",
    ),
    "SHELTER_INFO": (
        "shelter is open with space for families",
        "evacuation centre has available beds",
        "আশ্রয়কেন্দ্র খোলা আছে থাকার জায়গা আছে",
    ),
    "HAZARD_UPDATE": (
        "flood water rising road blocked bridge damaged",
        "fire building collapsed dangerous area",
        "বন্যার পানি বাড়ছে রাস্তা বন্ধ ভবন ধসে গেছে",
    ),
    "SAFE_ROUTE": (
        "this road is safe use the eastern route",
        "open evacuation route avoid the blocked bridge",
        "এই রাস্তা নিরাপদ বিকল্প পথে চলুন",
    ),
    "INSTRUCTION": (
        "official instruction evacuate now follow responder guidance",
        "boil water and remain indoors until further notice",
        "নির্দেশনা এখনই সরে যান ঘরের ভিতরে থাকুন",
    ),
}

_TYPE_SIGNALS: dict[ReportType, tuple[str, ...]] = {
    "SOS": ("help", "save us", "rescue", "trapped", "drowning", "বাঁচান", "উদ্ধার", "আটকা"),
    "MEDICAL_NEED": (
        "doctor",
        "medicine",
        "ambulance",
        "injured",
        "bleeding",
        "ডাক্তার",
        "ওষুধ",
        "অ্যাম্বুলেন্স",
        "আহত",
        "রক্তপাত",
    ),
    "RESOURCE_NEED": ("water", "food", "supplies", "পানি", "খাবার", "ত্রাণ"),
    "SAFETY_STATUS": ("safe", "missing", "নিরাপদ", "নিখোঁজ"),
    "SHELTER_INFO": ("shelter", "evacuation centre", "আশ্রয়", "আশ্রয়"),
    "HAZARD_UPDATE": (
        "flood",
        "fire",
        "collapsed",
        "blocked",
        "বন্যা",
        "আগুন",
        "ধসে",
        "বন্ধ",
    ),
    "SAFE_ROUTE": ("safe route", "open road", "বিকল্প পথ", "নিরাপদ রাস্তা"),
    "INSTRUCTION": ("instruction", "evacuate", "নির্দেশনা", "সরে যান"),
}

_NEED_SIGNALS: dict[str, tuple[str, ...]] = {
    "rescue": ("rescue", "trapped", "drowning", "উদ্ধার", "আটকা", "ডুবে"),
    "medical": (
        "medical",
        "doctor",
        "injured",
        "bleeding",
        "ambulance",
        "চিকিৎসা",
        "ডাক্তার",
        "আহত",
        "রক্তপাত",
    ),
    "water": ("water", "পানি", "জল"),
    "food": ("food", "খাবার"),
    "shelter": ("shelter", "আশ্রয়", "আশ্রয়"),
}

_CRITICAL_SIGNALS = (
    "drowning",
    "not breathing",
    "unconscious",
    "severe bleeding",
    "trapped under",
    "ডুবে যাচ্ছে",
    "শ্বাস নিচ্ছে না",
    "অচেতন",
    "প্রচণ্ড রক্তপাত",
    "নিচে চাপা",
)
_HIGH_SIGNALS = (
    "trapped",
    "bleeding",
    "injured",
    "fire",
    "collapsed",
    "আটকা",
    "রক্তপাত",
    "আহত",
    "আগুন",
    "ধসে",
)
_MEDIUM_SIGNALS = ("flood", "blocked", "water", "food", "বন্যা", "বন্ধ", "পানি", "খাবার")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.casefold())


def _contains(text: str, phrase: str) -> bool:
    normalized = text.casefold()
    signal = phrase.casefold()
    if signal.isascii():
        return (
            re.search(rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])", normalized)
            is not None
        )
    return signal in normalized


@dataclass(frozen=True)
class _TfidfModel:
    idf: dict[str, float]
    centroids: dict[ReportType, dict[str, float]]

    @classmethod
    def train(cls, examples: dict[ReportType, tuple[str, ...]]) -> _TfidfModel:
        documents = [
            (label, _tokens(text))
            for label, texts in examples.items()
            for text in texts
        ]
        document_frequency: Counter[str] = Counter()
        for _, tokens in documents:
            document_frequency.update(set(tokens))

        document_count = len(documents)
        idf = {
            token: math.log((1 + document_count) / (1 + frequency)) + 1
            for token, frequency in document_frequency.items()
        }
        vectors_by_label: dict[ReportType, list[dict[str, float]]] = defaultdict(list)
        for label, tokens in documents:
            vectors_by_label[label].append(_vector(tokens, idf))

        centroids = {
            label: _normalise(_mean_vector(vectors))
            for label, vectors in vectors_by_label.items()
        }
        return cls(idf=idf, centroids=centroids)

    def scores(self, text: str) -> dict[ReportType, float]:
        vector = _normalise(_vector(_tokens(text), self.idf))
        return {
            label: sum(
                weight * centroid.get(token, 0.0) for token, weight in vector.items()
            )
            for label, centroid in self.centroids.items()
        }


def _vector(tokens: Iterable[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(token for token in tokens if token in idf)
    total = sum(counts.values())
    if total == 0:
        return {}
    return {token: (count / total) * idf[token] for token, count in counts.items()}


def _normalise(vector: dict[str, float]) -> dict[str, float]:
    magnitude = math.sqrt(sum(weight * weight for weight in vector.values()))
    if magnitude == 0:
        return {}
    return {token: weight / magnitude for token, weight in vector.items()}


def _mean_vector(vectors: list[dict[str, float]]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for vector in vectors:
        for token, weight in vector.items():
            totals[token] += weight
    return {token: total / len(vectors) for token, total in totals.items()}


_TYPE_MODEL = _TfidfModel.train(_TRAINING_EXAMPLES)


def _classify_type(text: str, claimed_type: ReportType) -> ReportType:
    scores = _TYPE_MODEL.scores(text)
    for report_type, signals in _TYPE_SIGNALS.items():
        scores[report_type] += 0.2 * sum(_contains(text, signal) for signal in signals)

    best_type = max(scores, key=scores.get)
    # Sparse or unfamiliar text is safer left as the sender's structured type.
    return best_type if scores[best_type] >= 0.2 else claimed_type


def _extract_needs(text: str, declared_needs: list[str]) -> list[str]:
    needs: list[str] = []
    for need in declared_needs:
        normalized = need.strip().casefold()
        if normalized and normalized not in needs:
            needs.append(normalized)
    for need, signals in _NEED_SIGNALS.items():
        if need not in needs and any(_contains(text, signal) for signal in signals):
            needs.append(need)
    return needs[:20]


def _priority(
    text: str, report_type: ReportType, people_count: int | None, needs: list[str]
) -> Priority:
    if any(_contains(text, signal) for signal in _CRITICAL_SIGNALS):
        return "critical"
    if people_count is not None and people_count >= 10:
        return "critical"
    if any(_contains(text, signal) for signal in _HIGH_SIGNALS):
        return "high"
    if people_count is not None and people_count >= 3:
        return "high"
    if (
        report_type in {"SOS", "MEDICAL_NEED"}
        or "rescue" in needs
        or "medical" in needs
    ):
        return "high"
    if any(_contains(text, signal) for signal in _MEDIUM_SIGNALS):
        return "medium"
    if report_type in {"RESOURCE_NEED", "HAZARD_UPDATE", "SHELTER_INFO"}:
        return "medium"
    return "low"


@dataclass(frozen=True)
class RuleBasedClassifier:
    """Transparent default used until a real trained checkpoint is configured."""

    model_name: str = RULE_MODEL_NAME

    def classify_type(self, text: str, claimed_type: ReportType) -> ReportType:
        return _classify_type(text, claimed_type)


class TypeClassifier(Protocol):
    model_name: str

    def classify_type(self, text: str, claimed_type: ReportType) -> ReportType: ...


def build_classifier(fine_tuned_model_path: str | None = None) -> TypeClassifier:
    """Return the active type classifier without ever downloading a model.

    A supplied checkpoint is intentionally loaded eagerly: using a configured
    model path but silently falling back to rules would make operational model
    provenance false. The optional dependency is imported only in that path.
    """

    if fine_tuned_model_path is None:
        return RuleBasedClassifier()
    from .model_classifier import FineTunedClassifier

    return FineTunedClassifier.load(fine_tuned_model_path)


def classify_report(
    report: ClassificationReport, classifier: TypeClassifier | None = None
) -> ClassificationResult:
    active_classifier = classifier or RuleBasedClassifier()
    report_type = active_classifier.classify_type(report.payload.text, report.type)
    needs = _extract_needs(report.payload.text, report.payload.needs)
    return ClassificationResult(
        type=report_type,
        needs=needs,
        priority=_priority(
            report.payload.text, report_type, report.payload.people_count, needs
        ),
        model=active_classifier.model_name,
    )
