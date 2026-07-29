"""Inference adapter for an explicitly fine-tuned local BanglaBERT checkpoint.

The base ``csebuetnlp/banglabert`` checkpoint is an ELECTRA pretraining model,
not a crisis classifier. This adapter accepts only a local sequence-
classification checkpoint produced by :mod:`protidhoni_ai.fine_tuning`; it
never downloads weights at API startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, get_args

from .schemas import ReportType

_EXPECTED_LABELS = frozenset(get_args(ReportType))


def _normalise_bangla(text: str) -> str:
    try:
        from normalizer import normalize
    except ImportError as error:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "A fine-tuned BanglaBERT model requires csebuetnlp/normalizer. "
            "Install it with: pip install git+https://github.com/csebuetnlp/normalizer"
        ) from error
    return normalize(text)


@dataclass
class FineTunedClassifier:
    model_name: str
    _tokenizer: Any
    _model: Any
    _torch: Any
    _labels_by_index: tuple[ReportType, ...]

    @classmethod
    def load(cls, raw_path: str) -> "FineTunedClassifier":
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError(
                f"Configured fine-tuned model directory does not exist: {path}"
            )
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as error:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "Fine-tuned model support requires: pip install -e '.[model]'"
            ) from error

        try:
            tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(
                path, local_files_only=True
            )
        except Exception as error:  # invalid local checkpoint must stop startup
            raise RuntimeError(
                f"Could not load fine-tuned classifier from {path}: {error}"
            ) from error

        raw_labels = getattr(model.config, "id2label", {})
        labels = tuple(
            str(raw_labels.get(index, raw_labels.get(str(index), "")))
            for index in range(int(model.config.num_labels))
        )
        if len(labels) != len(_EXPECTED_LABELS) or set(labels) != _EXPECTED_LABELS:
            raise RuntimeError(
                "Fine-tuned classifier labels must contain every frozen report type exactly once."
            )
        model.eval()
        return cls(
            model_name=f"fine-tuned:{path.name}",
            _tokenizer=tokenizer,
            _model=model,
            _torch=torch,
            _labels_by_index=cast(tuple[ReportType, ...], labels),
        )

    def classify_type(self, text: str, claimed_type: ReportType) -> ReportType:
        del claimed_type  # A trained classifier deliberately decides this field.
        encoded = self._tokenizer(
            _normalise_bangla(text),
            return_tensors="pt",
            truncation=True,
            max_length=256,
        )
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits
            index = int(self._torch.argmax(logits, dim=-1).item())
        return self._labels_by_index[index]
