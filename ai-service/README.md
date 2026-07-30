# AI service — Person C

This service is a separately deployed process: it never imports backend code or writes directly to the database. Phase 1 implements the frozen `POST /ai/classify` response contract behind the `X-Internal-Service-Token` header.

## Active classifier and Phase 2 fine-tuning

The default classifier is `phase1-tfidf-rules-v1`: a small bilingual TF-IDF model trained from transparent examples in `src/protidhoni_ai/classifier.py`, plus explicit Bangla/English rules for structured needs and urgency. It returns a refined `type`, extracted `needs`, and `priority` (`critical` through `low`). This is deliberately lightweight and deterministic for the core demo path.

It is not presented as BanglaBERT output. A real local fine-tuned checkpoint can be enabled with `PROTIDHONI_FINE_TUNED_MODEL_PATH`. When that variable is absent, the rules classifier is deliberately used. When it is set but invalid or the optional model dependencies are absent, the service fails clearly at startup; it never silently changes model provenance.

BanglaBERT is a pretrained ELECTRA discriminator, not a crisis classifier. The model card requires its Bangla normalization pipeline for downstream fine-tuning, so install it explicitly alongside the optional dependencies:

```powershell
pip install -e ".[model]"
pip install git+https://github.com/csebuetnlp/normalizer
```

Prepare JSONL data with exactly `text` and `type` on each line. `type` must be one of the eight frozen report types. The training command rejects missing classes and datasets with fewer than four examples per class; use a substantially larger independently reviewed dataset for a credible demo evaluation.

```powershell
$env:PYTHONPATH = "src"
python -m protidhoni_ai.fine_tuning `
  --data .\data\crisis-training.jsonl `
  --eval-data .\data\crisis-evaluation.jsonl `
  --output .\artifacts\banglabert-crisis-v1

$env:PROTIDHONI_FINE_TUNED_MODEL_PATH = ".\artifacts\banglabert-crisis-v1"
uvicorn protidhoni_ai.main:app --port 8001
```

The generated `training_manifest.json` records the base model, frozen labels, training/evaluation dataset hashes, parameters, accuracy, and macro-F1. Never evaluate against the training file. Do not commit downloaded model weights or real crisis text to this repository.

```powershell
$env:PROTIDHONI_AI_INTERNAL_TOKEN = "replace-with-at-least-32-random-characters"
$env:PYTHONPATH = "src"
uvicorn protidhoni_ai.main:app --port 8001
```

## Base-model verification

The selected base model is [`csebuetnlp/banglabert`](https://huggingface.co/csebuetnlp/banglabert), the official BUET CSE NLP Group BanglaBERT model. It is a pretrained language model, **not** a crisis classifier; Phase 2 must fine-tune and evaluate it against a labeled crisis dataset before it is used for report classification.

Install the optional model dependency in an isolated environment, then run the explicit probe. It downloads the configured model only when `--download` is supplied, so ordinary API startup never silently consumes bandwidth or disk.

```powershell
pip install -e ".[model]"
$env:PYTHONPATH = "src"
python -m protidhoni_ai.model_probe --download
```

The probe loads the tokenizer and pretrained model, runs one Bangla tokenization, and prints its result. No model output is presented as an emergency assessment.

## Translation boundary

`src/protidhoni_ai/translation.py` provides an opt-in adapter for a self-hosted or managed LibreTranslate-compatible provider. Configure `PROTIDHONI_TRANSLATION_BASE_URL` and, when needed, `PROTIDHONI_TRANSLATION_API_KEY`. It sends plain text only when a caller explicitly requests a translation; otherwise it raises a clear unavailable error and the original report text must remain visible.

The base URL must be an HTTP(S) origin, without `/translate`, credentials, a query, or a fragment; the adapter appends `/translate` itself. When LibreTranslate runs directly on the Windows host at port 5000 while the AI service runs in Docker Desktop, use `TRANSLATION_BASE_URL=http://host.docker.internal:5000` in the repository `.env` and leave `TRANSLATION_API_KEY=` blank unless that instance explicitly enables API keys. When both are Compose services, use the provider's Compose service name instead of `localhost`.

The approved `1.2.0-phase2` contract exposes `POST /ai/translate` only to the backend over the internal service network. It requires `X-Internal-Service-Token`, accepts exactly `{text, source_language, target_language}`, and returns a labelled provider result. The public dashboard calls the backend's responder-authorized `POST /translations` endpoint with a report ID; it never receives this internal credential or sends raw report text directly to a provider.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```
