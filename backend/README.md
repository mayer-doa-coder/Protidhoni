# Backend — Person A

Phase 0 deliberately implements only a health endpoint. The full route contract is frozen in `../contracts/openapi.yaml`; Phase 1 adds report persistence and public API behavior after all clients have agreed on the contract.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:PYTHONPATH = "src"
uvicorn protidhoni_api.main:app --reload
```

Check `GET http://localhost:8000/health`. The containerized full stack is started from the repository root with `docker compose up --build` after copying `.env.example` to `.env` and setting real local-only values.

## Deployment hand-off

The Docker image is deployment-ready. Person A must connect this repository to the selected Render, Railway, or Fly.io project and set `PROTIDHONI_DATABASE_URL` and `PROTIDHONI_AI_INTERNAL_TOKEN` as platform secrets; that account-level action is intentionally not performed from this repository.
