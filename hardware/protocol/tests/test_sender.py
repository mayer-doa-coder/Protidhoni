from __future__ import annotations

import io
import importlib.metadata
import json
import uuid
from pathlib import Path

import pytest

from protidhoni_lora_protocol import APPLICATION_PORT, encode_report
from protidhoni_lora_protocol.sender import (
    MAX_JSON_INPUT_BYTES,
    SendPlan,
    SenderConfigurationError,
    SenderDependencyError,
    SenderOptions,
    SenderTransportError,
    build_send_plan,
    load_report_bytes,
    read_report,
    run_cli,
    send_plan,
    validate_options,
    _meshtastic_interface_factory,
)


def _report(*, text: str = "Sensitive rescue details", message_id: str | None = None) -> dict:
    return {
        "schema_version": "1.0.0",
        "message_id": message_id or str(uuid.uuid4()),
        "type": "SOS",
        "sender_pubkey": "A" * 43,
        "sender_pubkey_hash": "B" * 43,
        "created_at": "2026-07-30T09:15:00Z",
        "language": "en",
        "location": {"lat": 23.81, "lng": 90.41, "accuracy_m": 5, "source": "gps"},
        "payload": {
            "text": text,
            "people_count": 2,
            "needs": ["rescue"],
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": 5,
        "signature": {"algorithm": "Ed25519", "value": "C" * 86},
        "relay_path": [],
        "sync_status": "local",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }


class FakeInterface:
    def __init__(self, *, fail_at: int | None = None, fail_close: bool = False) -> None:
        self.calls: list[tuple[bytes, str, dict]] = []
        self.fail_at = fail_at
        self.fail_close = fail_close
        self.closed = 0

    def sendData(self, data: bytes, destinationId: str, **kwargs):  # noqa: N802, ANN003
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise OSError("simulated send failure")
        self.calls.append((data, destinationId, kwargs))
        return {"id": len(self.calls)}

    def close(self) -> None:
        self.closed += 1
        if self.fail_close:
            raise OSError("simulated close failure")


def test_load_report_rejects_ambiguous_or_unbounded_json() -> None:
    with pytest.raises(SenderConfigurationError, match="duplicate key"):
        load_report_bytes(b'{"message_id":"first","message_id":"second"}')
    with pytest.raises(SenderConfigurationError, match="not permitted"):
        load_report_bytes(b'{"message_id":NaN}')
    with pytest.raises(SenderConfigurationError, match="valid UTF-8"):
        load_report_bytes(b"\xff")
    with pytest.raises(SenderConfigurationError, match="one report object"):
        load_report_bytes(b"[]")
    with pytest.raises(SenderConfigurationError, match="input limit"):
        load_report_bytes(b" " * (MAX_JSON_INPUT_BYTES + 1))


def test_read_report_is_bounded_for_files_and_standard_input(tmp_path: Path) -> None:
    raw = json.dumps(_report(), ensure_ascii=False).encode()
    path = tmp_path / "report.json"
    path.write_bytes(raw)
    assert read_report(str(path)) == json.loads(raw)
    assert read_report("-", stdin=io.BytesIO(raw)) == json.loads(raw)

    path.write_bytes(b"x" * (MAX_JSON_INPUT_BYTES + 1))
    with pytest.raises(SenderConfigurationError, match="input limit"):
        read_report(str(path))


def test_build_send_plan_uses_the_frozen_ordered_codec() -> None:
    report = _report(text="জরুরি সহায়তা দরকার " * 30)
    plan = build_send_plan(report)
    assert plan.message_id == uuid.UUID(report["message_id"])
    assert plan.frames == tuple(encode_report(report))
    assert plan.frame_count > 1
    assert plan.canonical_payload_size > 0


@pytest.mark.parametrize(
    "options",
    [
        SenderOptions(host=""),
        SenderOptions(port=0),
        SenderOptions(destination="node-1"),
        SenderOptions(channel_index=8),
        SenderOptions(hop_limit=0),
        SenderOptions(interval_seconds=61),
        SenderOptions(connect_timeout_seconds=301),
    ],
)
def test_sender_options_fail_closed(options: SenderOptions) -> None:
    with pytest.raises(SenderConfigurationError):
        validate_options(options)


def test_send_plan_uses_private_app_metadata_order_and_pacing() -> None:
    plan = build_send_plan(_report(text="x" * 700))
    fake = FakeInterface()
    factory_calls: list[tuple[str, int, int]] = []
    sleeps: list[float] = []

    def factory(host: str, port: int, timeout: int) -> FakeInterface:
        factory_calls.append((host, port, timeout))
        return fake

    options = SenderOptions(
        host="127.0.0.1",
        port=4403,
        destination="!1a2b3c4d",
        channel_index=2,
        hop_limit=4,
        interval_seconds=0.25,
        connect_timeout_seconds=20,
    )
    assert send_plan(plan, options, interface_factory=factory, sleeper=sleeps.append) == len(
        plan.frames
    )
    assert factory_calls == [("127.0.0.1", 4403, 20)]
    assert [call[0] for call in fake.calls] == list(plan.frames)
    assert all(call[1] == "!1a2b3c4d" for call in fake.calls)
    assert all(
        call[2]
        == {
            "portNum": APPLICATION_PORT,
            "wantAck": False,
            "channelIndex": 2,
            "hopLimit": 4,
        }
        for call in fake.calls
    )
    assert sleeps == [0.25] * (len(plan.frames) - 1)
    assert fake.closed == 1


def test_send_failure_is_precise_and_still_closes() -> None:
    plan = build_send_plan(_report())
    fake = FakeInterface(fail_at=1)
    with pytest.raises(SenderTransportError, match="fragment 2"):
        send_plan(plan, SenderOptions(interval_seconds=0), interface_factory=lambda *_: fake)
    assert fake.closed == 1


def test_close_failure_is_not_silently_ignored_after_success() -> None:
    plan = build_send_plan(_report())
    fake = FakeInterface(fail_close=True)
    with pytest.raises(SenderTransportError, match="failed to close"):
        send_plan(plan, SenderOptions(interval_seconds=0), interface_factory=lambda *_: fake)


def test_primary_send_failure_is_preserved_if_close_also_fails() -> None:
    plan = build_send_plan(_report())
    fake = FakeInterface(fail_at=0, fail_close=True)
    with pytest.raises(SenderTransportError, match="fragment 1"):
        send_plan(plan, SenderOptions(interval_seconds=0), interface_factory=lambda *_: fake)


def test_dry_run_opens_no_interface_and_prints_no_sensitive_fields(tmp_path: Path) -> None:
    report = _report(text="DO NOT PRINT THIS TEXT")
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    opened = False

    def forbidden_factory(*_args):
        nonlocal opened
        opened = True
        raise AssertionError("dry-run opened an interface")

    stdout = io.StringIO()
    stderr = io.StringIO()
    result = run_cli(
        [str(path), "--dry-run"],
        stdout=stdout,
        stderr=stderr,
        interface_factory=forbidden_factory,
    )
    output = stdout.getvalue()
    assert result == 0
    assert not opened
    assert stderr.getvalue() == ""
    assert report["message_id"] in output
    assert "DO NOT PRINT THIS TEXT" not in output
    assert report["sender_pubkey"] not in output
    assert "23.81" not in output
    assert "90.41" not in output
    assert "packets sent" in output


def test_cli_sends_with_injected_interface_and_safe_summary(tmp_path: Path) -> None:
    report = _report()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    fake = FakeInterface()
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run_cli(
        [str(path), "--interval-ms", "0", "--hop-limit", "5"],
        stdout=stdout,
        stderr=stderr,
        interface_factory=lambda *_: fake,
    )
    assert result == 0
    assert stderr.getvalue() == ""
    assert len(fake.calls) == len(encode_report(report))
    assert all(call[2]["hopLimit"] == 5 for call in fake.calls)
    assert "Sensitive rescue details" not in stdout.getvalue()


def test_cli_returns_failure_without_echoing_invalid_report_content(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"secret":"DO NOT ECHO",}', encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert run_cli([str(path), "--dry-run"], stdout=stdout, stderr=stderr) == 2
    assert stdout.getvalue() == ""
    assert "DO NOT ECHO" not in stderr.getvalue()
    assert "not valid JSON" in stderr.getvalue()


def test_interface_factory_failure_is_wrapped() -> None:
    plan = build_send_plan(_report())

    def fail_factory(*_args):
        raise OSError("connection refused")

    with pytest.raises(SenderTransportError, match="cannot connect"):
        send_plan(plan, SenderOptions(), interface_factory=fail_factory)


@pytest.mark.parametrize(
    "plan, message",
    [
        (SendPlan(uuid.uuid4(), 1, ()), "at least one frame"),
        (SendPlan(uuid.uuid4(), 1, (b"not-a-frame",)), "fragment 1 is invalid"),
    ],
)
def test_invalid_manual_send_plan_fails_before_connecting(plan: SendPlan, message: str) -> None:
    opened = False

    def forbidden_factory(*_args):
        nonlocal opened
        opened = True
        raise AssertionError("invalid plan opened an interface")

    with pytest.raises(SenderConfigurationError, match=message):
        send_plan(plan, SenderOptions(), interface_factory=forbidden_factory)
    assert not opened


def test_unexpected_upstream_errors_are_wrapped_and_close_is_attempted() -> None:
    plan = build_send_plan(_report())

    class UpstreamInterface(FakeInterface):
        def sendData(self, data: bytes, destinationId: str, **kwargs):  # noqa: N802, ANN003
            raise ValueError("upstream-specific failure")

    fake = UpstreamInterface()
    with pytest.raises(SenderTransportError, match="fragment 1"):
        send_plan(plan, SenderOptions(interval_seconds=0), interface_factory=lambda *_: fake)
    assert fake.closed == 1


def test_meshtastic_dependency_must_match_the_exact_reviewed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "2.7.12")
    with pytest.raises(SenderDependencyError, match="2.7.11 is required"):
        _meshtastic_interface_factory("127.0.0.1", 4403, 30)


def test_missing_meshtastic_dependency_has_an_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(SenderDependencyError, match=r"pip install -e"):
        _meshtastic_interface_factory("127.0.0.1", 4403, 30)
