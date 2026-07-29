"""Explicit local validation for the selected pretrained model."""

import argparse
from pathlib import Path

from .settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the configured BanglaBERT model locally."
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Allow a first-time download from Hugging Face instead of requiring a cached model.",
    )
    args = parser.parse_args()

    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as error:
        raise SystemExit(
            "Install optional dependencies first: pip install -e '.[model]'"
        ) from error

    model_id = get_settings().model_id
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, local_files_only=not args.download
    )
    model = AutoModel.from_pretrained(model_id, local_files_only=not args.download)
    encoded = tokenizer("জরুরি চিকিৎসা সহায়তা দরকার", return_tensors="pt")
    if encoded.input_ids.shape[1] < 2:
        raise SystemExit("Tokenizer returned an invalid sequence.")

    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    print(f"model={model_id}")
    print(f"cache={Path(tokenizer.name_or_path)}")
    print(f"token_count={encoded.input_ids.shape[1]}")
    print(f"parameters={parameter_count}")


if __name__ == "__main__":
    main()
