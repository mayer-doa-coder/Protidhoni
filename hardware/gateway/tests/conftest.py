from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

VECTORS_PATH = Path(__file__).resolve().parents[2] / "protocol" / "vectors" / "golden-v1.json"


@pytest.fixture
def signed_report() -> dict:
    document = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(document["vectors"][0]["report"])
