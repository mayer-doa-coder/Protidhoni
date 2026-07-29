# AI service — Person C

This service is a separately deployed process: it never imports backend code or writes directly to the database. Phase 1 implements the frozen `POST /ai/classify` response contract behind the `X-Internal-Service-Token` header.

## Phase 1 classifier

The active classifier is `phase1-tfidf-rules-v1`: a small bilingual TF-IDF model trained from transparent examples in `src/protidhoni_ai/classifier.py`, plus explicit Bangla/English rules for structured needs and urgency. It returns a refined `type`, extracted `needs`, and `priority` (`critical` through `low`). This is deliberately lightweight and deterministic for the core demo path.

It is not presented as BanglaBERT output. The backend still needs to invoke this service after accepting a report and persist the enrichment; Person A's current Phase 1 branch does not yet contain that orchestration step.

```powershell
$env:PROTIDHONI_AI_INTERNAL_TOKEN = "replace-with-a-shared-secret"
$env:PYTHONPATH = "src"
uvicorn protidhoni_ai.main:app --port 8001
```

## Phase 0 model verification

The selected base model is [`csebuetnlp/banglabert`](https://huggingface.co/csebuetnlp/banglabert), the official BUET CSE NLP Group BanglaBERT model. It is a pretrained language model, **not** a crisis classifier; Phase 2 must fine-tune and evaluate it against a labeled crisis dataset before it is used for report classification.

Install the optional model dependency in an isolated environment, then run the explicit probe. It downloads the configured model only when `--download` is supplied, so ordinary API startup never silently consumes bandwidth or disk.

```powershell
pip install -e ".[model]"
$env:PYTHONPATH = "src"
python -m protidhoni_ai.model_probe --download
```

The probe loads the tokenizer and pretrained model, runs one Bangla tokenization, and prints its result. No model output is presented as an emergency assessment.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```
