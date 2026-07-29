"""Reproducible local fine-tuning for the frozen crisis-report type labels.

This command is intentionally separate from API startup. It requires an
explicit labelled JSONL dataset and writes a local checkpoint; no downloaded
or unvalidated model is ever presented as an active crisis classifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args

from .schemas import ReportType

LABELS: tuple[ReportType, ...] = get_args(ReportType)
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


@dataclass(frozen=True)
class LabelledExample:
    text: str
    type: ReportType


def load_labelled_examples(
    path: Path, *, minimum_examples_per_label: int = 4
) -> list[LabelledExample]:
    examples: list[LabelledExample] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from error
        if not isinstance(raw, dict) or set(raw) != {"text", "type"}:
            raise ValueError(f"{path}:{line_number} must contain exactly text and type")
        text, label = raw["text"], raw["type"]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError(
                f"{path}:{line_number} text must contain 1-2000 characters"
            )
        if label not in LABEL_TO_ID:
            raise ValueError(f"{path}:{line_number} has an unknown frozen report type")
        examples.append(LabelledExample(text=text.strip(), type=label))

    counts = Counter(example.type for example in examples)
    insufficient = [
        label for label in LABELS if counts[label] < minimum_examples_per_label
    ]
    if insufficient:
        raise ValueError(
            f"{path} needs at least {minimum_examples_per_label} examples for every report type; "
            f"insufficient: {', '.join(insufficient)}"
        )
    return examples


def _normalise_bangla(text: str) -> str:
    try:
        from normalizer import normalize
    except ImportError as error:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "BanglaBERT fine-tuning requires csebuetnlp/normalizer. Install it with: "
            "pip install git+https://github.com/csebuetnlp/normalizer"
        ) from error
    return normalize(text)


def train_classifier(
    *,
    data_path: Path,
    eval_data_path: Path,
    output_dir: Path,
    base_model: str,
    epochs: float,
    batch_size: int,
    learning_rate: float,
) -> None:
    if output_dir.exists():
        raise ValueError(f"Refusing to overwrite existing model output: {output_dir}")
    examples = load_labelled_examples(data_path)
    evaluation_examples = load_labelled_examples(
        eval_data_path, minimum_examples_per_label=1
    )
    try:
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError as error:  # pragma: no cover - optional dependency path
        raise RuntimeError("Fine-tuning requires: pip install -e '.[model]'") from error

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        num_labels=len(LABELS),
        id2label=dict(enumerate(LABELS)),
        label2id=LABEL_TO_ID,
        ignore_mismatched_sizes=True,
    )

    class CrisisDataset(torch.utils.data.Dataset):
        def __init__(self, rows: list[LabelledExample]) -> None:
            self._rows = rows
            self._encoded = tokenizer(
                [_normalise_bangla(example.text) for example in rows],
                truncation=True,
                max_length=256,
                padding=True,
            )

        def __len__(self) -> int:
            return len(self._rows)

        def __getitem__(self, index: int) -> dict[str, Any]:
            item = {
                key: torch.tensor(value[index]) for key, value in self._encoded.items()
            }
            item["labels"] = torch.tensor(LABEL_TO_ID[self._rows[index].type])
            return item

    output_dir.mkdir(parents=True)
    training_dataset = CrisisDataset(examples)
    evaluation_dataset = CrisisDataset(evaluation_examples)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=learning_rate,
            save_strategy="no",
            report_to=[],
            seed=42,
        ),
        train_dataset=training_dataset,
    )
    trainer.train()
    logits = trainer.predict(evaluation_dataset).predictions
    predicted_label_ids = [int(row.argmax()) for row in logits]
    expected_label_ids = [LABEL_TO_ID[example.type] for example in evaluation_examples]
    metrics = classification_metrics(predicted_label_ids, expected_label_ids)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(output_dir)
    (output_dir / "training_manifest.json").write_text(
        json.dumps(
            {
                "base_model": base_model,
                "labels": list(LABELS),
                "examples": len(examples),
                "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
                "evaluation_examples": len(evaluation_examples),
                "evaluation_dataset_sha256": hashlib.sha256(
                    eval_data_path.read_bytes()
                ).hexdigest(),
                "evaluation_metrics": metrics,
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def classification_metrics(
    predicted_label_ids: list[int], expected_label_ids: list[int]
) -> dict[str, float]:
    if not expected_label_ids or len(predicted_label_ids) != len(expected_label_ids):
        raise ValueError(
            "Predictions and expected labels must be non-empty and equally sized."
        )
    macro_f1 = 0.0
    for label_id in range(len(LABELS)):
        true_positive = sum(
            predicted == label_id and expected == label_id
            for predicted, expected in zip(predicted_label_ids, expected_label_ids)
        )
        false_positive = sum(
            predicted == label_id and expected != label_id
            for predicted, expected in zip(predicted_label_ids, expected_label_ids)
        )
        false_negative = sum(
            predicted != label_id and expected == label_id
            for predicted, expected in zip(predicted_label_ids, expected_label_ids)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        macro_f1 += 0.0 if denominator == 0 else (2 * true_positive) / denominator
    return {
        "accuracy": sum(
            predicted == expected
            for predicted, expected in zip(predicted_label_ids, expected_label_ids)
        )
        / len(expected_label_ids),
        "macro_f1": macro_f1 / len(LABELS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune BanglaBERT for Protidhoni report types."
    )
    parser.add_argument(
        "--data", required=True, type=Path, help="JSONL rows: {text, type}"
    )
    parser.add_argument(
        "--eval-data",
        required=True,
        type=Path,
        help="Held-out JSONL rows: {text, type}; never reuse training data",
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="New local checkpoint directory"
    )
    parser.add_argument("--base-model", default="csebuetnlp/banglabert")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    args = parser.parse_args()
    if args.epochs <= 0 or args.batch_size < 1 or args.learning_rate <= 0:
        raise SystemExit("epochs, batch-size, and learning-rate must be positive.")
    train_classifier(
        data_path=args.data,
        eval_data_path=args.eval_data,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )


if __name__ == "__main__":
    main()
