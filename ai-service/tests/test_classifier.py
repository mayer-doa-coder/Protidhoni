from protidhoni_ai.classifier import classify_report
from protidhoni_ai.schemas import ClassificationReport

from .factories import make_report


def classify(**report_values):
    report = ClassificationReport.model_validate(make_report(**report_values))
    return classify_report(report)


def test_bangla_rescue_is_high_priority_sos_with_extracted_need() -> None:
    result = classify(text="বন্যার পানিতে তিনজন আটকা পড়েছে, দ্রুত উদ্ধার দরকার", people_count=3)

    assert result.type == "SOS"
    assert result.priority == "high"
    assert result.needs == ["rescue", "water"]


def test_immediate_life_threat_is_critical() -> None:
    result = classify(
        text="One person is not breathing and needs an ambulance", language="en"
    )

    assert result.type == "MEDICAL_NEED"
    assert result.priority == "critical"
    assert result.needs == ["medical"]


def test_resource_report_preserves_declared_needs_and_extracts_new_ones() -> None:
    result = classify(
        text="Families need drinking water and food",
        report_type="RESOURCE_NEED",
        language="en",
        needs=["shelter", "water"],
    )

    assert result.type == "RESOURCE_NEED"
    assert result.priority == "medium"
    assert result.needs == ["shelter", "water", "food"]


def test_unfamiliar_text_keeps_the_structured_sender_type() -> None:
    result = classify(
        text="Community update number 42",
        report_type="SAFETY_STATUS",
        language="en",
    )

    assert result.type == "SAFETY_STATUS"
    assert result.priority == "low"
