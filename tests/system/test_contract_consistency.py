"""Executable checks that the frozen contracts still match both Python services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import yaml

from protidhoni_ai.main import create_app as create_ai_app
from protidhoni_ai.schemas import ReportType as AiReportType
from protidhoni_ai.settings import Settings as AiSettings
from protidhoni_api.main import create_app as create_backend_app
from protidhoni_api.models import ReportType as BackendReportType

ROOT = Path(__file__).resolve().parents[2]
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _operations(spec: dict) -> set[tuple[str, str]]:
    return {
        (path, method)
        for path, path_item in spec["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }


def test_frozen_openapi_operations_match_the_two_runtime_apps() -> None:
    frozen = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    backend = create_backend_app().openapi()
    ai = create_ai_app(AiSettings(ai_internal_token="x" * 32)).openapi()

    assert _operations(frozen) == _operations(backend) | _operations(ai)


def test_privileged_contract_operations_require_the_documented_credentials() -> None:
    frozen = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    expected = {
        ("/reports/{message_id}", "patch"): "ResponderToken",
        ("/instructions", "post"): "ResponderToken",
        ("/translations", "post"): "ResponderToken",
        ("/ai/classify", "post"): "InternalServiceToken",
        ("/ai/translate", "post"): "InternalServiceToken",
    }
    for (path, method), scheme in expected.items():
        assert {scheme: []} in frozen["paths"][path][method]["security"]


def test_report_type_enums_match_the_frozen_message_schema() -> None:
    schema = json.loads((ROOT / "contracts/message-schema.json").read_text(encoding="utf-8"))
    frozen_types = set(schema["$defs"]["report"]["properties"]["type"]["enum"])

    assert set(get_args(BackendReportType)) == frozen_types
    assert set(get_args(AiReportType)) == frozen_types
