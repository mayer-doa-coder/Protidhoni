"""Meshtastic 2.7.11 TCP/pubsub adapter."""

from __future__ import annotations

import importlib.metadata
import logging
from collections.abc import Callable, Mapping
from threading import Event
from typing import Protocol

from protidhoni_lora_protocol import APPLICATION_PORT

logger = logging.getLogger(__name__)

MESHTASTIC_PYTHON_VERSION = "2.7.11"
RECEIVE_TOPIC = "meshtastic.receive"


class ReceiverError(RuntimeError):
    """Base class for an expected Meshtastic adapter failure."""


class ReceiverDependencyError(ReceiverError):
    """The exact reviewed Meshtastic dependency is unavailable."""


class ReceiverTransportError(ReceiverError):
    """The TCP interface could not connect or remain healthy."""


class MeshtasticInterface(Protocol):
    failure: object | None

    def close(self) -> None: ...


class PubSubBus(Protocol):
    def subscribe(self, listener: Callable[..., object], topic_name: str) -> object: ...

    def unsubscribe(self, listener: Callable[..., object], topic_name: str) -> object: ...


InterfaceFactory = Callable[[str, int, int], MeshtasticInterface]
DependencyLoader = Callable[[], tuple[PubSubBus, InterfaceFactory]]


def extract_private_app_payload(packet: object) -> bytes | None:
    """Return one binary PRIVATE_APP payload, or ignore an unrelated packet."""

    if not isinstance(packet, Mapping):
        return None
    decoded = packet.get("decoded")
    if not isinstance(decoded, Mapping):
        return None
    port_number = decoded.get("portnum")
    if port_number != "PRIVATE_APP" and port_number != APPLICATION_PORT:
        return None
    payload = decoded.get("payload")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        return None
    return bytes(payload)


def _load_meshtastic() -> tuple[PubSubBus, InterfaceFactory]:
    try:
        installed_version = importlib.metadata.version("meshtastic")
    except importlib.metadata.PackageNotFoundError as error:
        raise ReceiverDependencyError(
            "Meshtastic client is not installed; install the gateway package dependencies"
        ) from error
    if installed_version != MESHTASTIC_PYTHON_VERSION:
        raise ReceiverDependencyError(
            f"Meshtastic client {MESHTASTIC_PYTHON_VERSION} is required; found {installed_version}"
        )

    try:
        from meshtastic.tcp_interface import TCPInterface
        from pubsub import pub
    except ImportError as error:
        raise ReceiverDependencyError(
            "the installed Meshtastic TCP/pubsub interface cannot be imported"
        ) from error

    def factory(host: str, port: int, timeout: int) -> MeshtasticInterface:
        return TCPInterface(hostname=host, portNumber=port, timeout=timeout)

    return pub, factory


class MeshtasticReceiver:
    """Subscribe before connecting, then keep the TCP interface alive until stopped."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        dependency_loader: DependencyLoader = _load_meshtastic,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout_seconds = connect_timeout_seconds
        self._dependency_loader = dependency_loader

    def run(
        self,
        on_frame: Callable[[bytes], bool],
        *,
        stop_event: Event,
        healthcheck: Callable[[], None] | None = None,
    ) -> None:
        pub, interface_factory = self._dependency_loader()

        def on_receive(packet: object, interface: object | None = None) -> None:
            del interface
            payload = extract_private_app_payload(packet)
            if payload is not None and not on_frame(payload):
                logger.warning("Dropped frame because the bounded worker queue is full")

        pub.subscribe(on_receive, RECEIVE_TOPIC)
        interface: MeshtasticInterface | None = None
        primary_error: Exception | None = None
        try:
            try:
                interface = interface_factory(
                    self.host,
                    self.port,
                    self.connect_timeout_seconds,
                )
            except Exception as error:
                raise ReceiverTransportError(
                    f"cannot connect to Meshtastic TCP node {self.host}:{self.port}"
                ) from error

            logger.info("Connected to Meshtastic TCP node %s:%s", self.host, self.port)
            while not stop_event.wait(0.25):
                if healthcheck is not None:
                    healthcheck()
                if interface.failure is not None:
                    raise ReceiverTransportError("Meshtastic TCP interface reported a failure")
        except Exception as error:
            primary_error = error
            raise
        finally:
            try:
                pub.unsubscribe(on_receive, RECEIVE_TOPIC)
            except Exception as error:
                if primary_error is None:
                    raise ReceiverTransportError(
                        "failed to unsubscribe the Meshtastic receive callback"
                    ) from error
            if interface is not None:
                try:
                    interface.close()
                except Exception as error:
                    if primary_error is None:
                        raise ReceiverTransportError(
                            "failed to close the Meshtastic TCP interface"
                        ) from error
