import json

import pytest

from protidhoni_ai.classifier import build_classifier
from protidhoni_ai.fine_tuning import (
    LABELS,
    classification_metrics,
    load_labelled_examples,
)


def write_dataset(path, *, missing_label: str | None = None) -> None:
    rows = [
        {"text": f"Example {index} for {label}", "type": label}
        for label in LABELS
        if label != missing_label
        for index in range(4)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_load_labelled_examples_requires_coverage_and_a_minimum_dataset(
    tmp_path,
) -> None:
    data = tmp_path / "training.jsonl"
    write_dataset(data)

    examples = load_labelled_examples(data)

    assert len(examples) == len(LABELS) * 4
    assert {example.type for example in examples} == set(LABELS)


def test_load_labelled_examples_rejects_missing_report_types(tmp_path) -> None:
    data = tmp_path / "incomplete.jsonl"
    write_dataset(data, missing_label="SOS")

    with pytest.raises(ValueError, match="insufficient: SOS"):
        load_labelled_examples(data)


def test_configured_missing_checkpoint_does_not_silently_use_rules(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="does not exist"):
        build_classifier(str(tmp_path / "missing-checkpoint"))


def test_classification_metrics_records_accuracy_and_macro_f1_for_every_label() -> None:
    expected = list(range(len(LABELS)))
    metrics = classification_metrics(expected, expected)

    assert metrics == {"accuracy": 1.0, "macro_f1": 1.0}

    one_wrong = classification_metrics([1, *expected[1:]], expected)
    assert 0 < one_wrong["accuracy"] < 1
    assert 0 < one_wrong["macro_f1"] < 1
