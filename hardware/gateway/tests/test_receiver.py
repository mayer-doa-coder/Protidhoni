from __future__ import annotations

import importlib.metadata
import threading

import pytest

from protidhoni_lora_gateway import receiver as receiver_module
from protidhoni_lora_gateway.receiver import (
    MESHTASTIC_PYTHON_VERSION,
    MeshtasticReceiver,
    ReceiverDependencyError,
    ReceiverTransportError,
    extract_private_app_payload,
)


@pytest.mark.parametrize("port", ["PRIVATE_APP", 256])
def test_private_app_binary_payload_is_extracted(port: object) -> None:
    assert (
        extract_private_app_payload({"decoded": {"portnum": port, "payload": bytearray(b"frame")}})
        == b"frame"
    )


@pytest.mark.parametrize(
    "packet",
    [
        None,
        {},
        {"decoded": "bad"},
        {"decoded": {"portnum": [], "payload": b"frame"}},
        {"decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": b"text"}},
        {"decoded": {"portnum": "PRIVATE_APP", "payload": "not bytes"}},
    ],
)
def test_unrelated_or_malformed_packets_are_ignored(packet: object) -> None:
    assert extract_private_app_payload(packet) is None


class FakePub:
    def __init__(self) -> None:
        self.listener = None
        self.subscribed = False
        self.unsubscribed = False

    def subscribe(self, listener, topic_name):
        assert topic_name == "meshtastic.receive"
        self.listener = listener
        self.subscribed = True

    def unsubscribe(self, listener, topic_name):
        assert listener is self.listener
        assert topic_name == "meshtastic.receive"
        self.unsubscribed = True


class FakeInterface:
    def __init__(self, failure=None) -> None:
        self.failure = failure
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_receiver_subscribes_before_connect_and_closes_cleanly() -> None:
    pub = FakePub()
    interface = FakeInterface()
    stop = threading.Event()
    frames: list[bytes] = []

    def factory(host: str, port: int, timeout: int) -> FakeInterface:
        assert pub.subscribed
        assert (host, port, timeout) == ("node", 4406, 30)
        assert pub.listener is not None
        pub.listener({"decoded": {"portnum": "PRIVATE_APP", "payload": b"frame"}})
        stop.set()
        return interface

    receiver = MeshtasticReceiver(
        host="node",
        port=4406,
        connect_timeout_seconds=30,
        dependency_loader=lambda: (pub, factory),
    )
    receiver.run(lambda frame: not frames.append(frame), stop_event=stop)
    assert frames == [b"frame"]
    assert pub.unsubscribed
    assert interface.closed == 1


def test_receiver_wraps_connection_failure_and_unsubscribes() -> None:
    pub = FakePub()

    def factory(*_args):
        raise OSError("connection refused")

    receiver = MeshtasticReceiver(
        host="node",
        port=4406,
        connect_timeout_seconds=30,
        dependency_loader=lambda: (pub, factory),
    )
    with pytest.raises(ReceiverTransportError, match="cannot connect"):
        receiver.run(lambda _frame: True, stop_event=threading.Event())
    assert pub.unsubscribed


def test_receiver_surfaces_an_interface_failure_and_closes() -> None:
    pub = FakePub()
    interface = FakeInterface(failure=RuntimeError("node stopped"))
    receiver = MeshtasticReceiver(
        host="node",
        port=4406,
        connect_timeout_seconds=30,
        dependency_loader=lambda: (pub, lambda *_args: interface),
    )
    with pytest.raises(ReceiverTransportError, match="reported a failure"):
        receiver.run(lambda _frame: True, stop_event=threading.Event())
    assert pub.unsubscribed
    assert interface.closed == 1


def test_exact_reviewed_meshtastic_version_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "2.7.12")
    with pytest.raises(ReceiverDependencyError, match=MESHTASTIC_PYTHON_VERSION):
        receiver_module._load_meshtastic()


def test_missing_meshtastic_dependency_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(ReceiverDependencyError, match="not installed"):
        receiver_module._load_meshtastic()
