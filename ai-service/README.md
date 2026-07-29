# AI service — Person C

This service is a separately deployed process: it never imports backend code or writes directly to the database. The backend will call it through the frozen `POST /ai/classify` contract in Phase 1.

## Phase 0 model verification

The selected base model is [`csebuetnlp/banglabert`](https://huggingface.co/csebuetnlp/banglabert), the official BUET CSE NLP Group BanglaBERT model. It is a pretrained language model, **not** a crisis classifier; Phase 2 must fine-tune and evaluate it against a labeled crisis dataset before it is used for report classification.

Install the optional model dependency in an isolated environment, then run the explicit probe. It downloads the configured model only when `--download` is supplied, so ordinary API startup never silently consumes bandwidth or disk.

```powershell
pip install -e ".[model]"
$env:PYTHONPATH = "src"
python -m protidhoni_ai.model_probe --download
```

The probe loads the tokenizer and pretrained model, runs one Bangla tokenization, and prints its result. No model output is presented as an emergency assessment.
