from pathlib import Path

from protidhoni_ai.settings import Settings


def test_blank_fine_tuned_model_path_env_disables_it(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_FINE_TUNED_MODEL_PATH", "")

    assert Settings().fine_tuned_model_path is None


def test_unset_fine_tuned_model_path_stays_none(monkeypatch) -> None:
    monkeypatch.delenv("PROTIDHONI_FINE_TUNED_MODEL_PATH", raising=False)

    assert Settings().fine_tuned_model_path is None


def test_configured_fine_tuned_model_path_is_preserved(monkeypatch) -> None:
    monkeypatch.setenv(
        "PROTIDHONI_FINE_TUNED_MODEL_PATH", "artifacts/banglabert-crisis-v2"
    )

    assert Settings().fine_tuned_model_path == Path("artifacts/banglabert-crisis-v2")
