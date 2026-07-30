"""Safe command-line sender for Meshtasticator's TCP interface.

The sender accepts an already signed report, applies the frozen codec, and sends
the resulting binary frames. It never creates or loads a signing private key.
"""

from __future__ import annotations

import argparse
import hmac
import importlib.metadata
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol, Sequence, TextIO
from uuid import UUID

from .codec import (
    APPLICATION_PORT,
    MAX_APPLICATION_PAYLOAD,
    ProtocolError,
    canonical_report_bytes,
    decode_frame,
    encode_report,
)

MESHTASTIC_PYTHON_VERSION = "2.7.11"
DEFAULT_TCP_HOST = "127.0.0.1"
DEFAULT_TCP_PORT = 4403
DEFAULT_HOP_LIMIT = 3
DEFAULT_CHANNEL_INDEX = 0
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30
MAX_JSON_INPUT_BYTES = 65_536
MAX_INTERVAL_SECONDS = 60.0
MAX_CONNECT_TIMEOUT_SECONDS = 300

_NODE_ID = re.compile(r"^![0-9A-Fa-f]{8}$")


class SenderError(RuntimeError):
    """Base class for an expected sender failure."""


class SenderConfigurationError(SenderError):
    """The local input or command configuration is invalid."""


class SenderDependencyError(SenderError):
    """The pinned Meshtastic client is unavailable."""


class SenderTransportError(SenderError):
    """Connecting, sending, or closing the TCP interface failed."""


class MeshtasticInterface(Protocol):
    def sendData(  # noqa: N802 - name is fixed by the upstream Meshtastic API
        self,
        data: bytes,
        destinationId: str,
        *,
        portNum: int,
        wantAck: bool,
        channelIndex: int,
        hopLimit: int,
    ) -> object: ...

    def close(self) -> None: ...


InterfaceFactory = Callable[[str, int, int], MeshtasticInterface]
Sleeper = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class SendPlan:
    message_id: UUID
    canonical_payload_size: int
    frames: tuple[bytes, ...]

    @property
    def frame_count(self) -> int:
        return len(self.frames)


@dataclass(frozen=True, slots=True)
class SenderOptions:
    host: str = DEFAULT_TCP_HOST
    port: int = DEFAULT_TCP_PORT
    destination: str = "^all"
    channel_index: int = DEFAULT_CHANNEL_INDEX
    hop_limit: int = DEFAULT_HOP_LIMIT
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS


def _reject_json_constant(value: str) -> None:
    raise SenderConfigurationError(f"JSON constant {value!r} is not permitted")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SenderConfigurationError(f"JSON object contains duplicate key {key!r}")
        result[key] = value
    return result


def load_report_bytes(raw: bytes, *, source_name: str = "input") -> dict[str, Any]:
    """Parse one bounded UTF-8 JSON report without accepting ambiguous JSON."""

    if len(raw) > MAX_JSON_INPUT_BYTES:
        raise SenderConfigurationError(
            f"{source_name} exceeds the {MAX_JSON_INPUT_BYTES}-byte JSON input limit"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SenderConfigurationError(f"{source_name} is not valid UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as error:
        raise SenderConfigurationError(
            f"{source_name} is not valid JSON: line {error.lineno}, column {error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise SenderConfigurationError(f"{source_name} must contain one report object")
    return value


def read_report(source: str, *, stdin: BinaryIO | None = None) -> dict[str, Any]:
    """Read a bounded report from a file path or standard input (`-`)."""

    if source == "-":
        stream = sys.stdin.buffer if stdin is None else stdin
        raw = stream.read(MAX_JSON_INPUT_BYTES + 1)
        return load_report_bytes(raw, source_name="standard input")

    path = Path(source)
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_INPUT_BYTES + 1)
    except OSError as error:
        raise SenderConfigurationError(f"cannot read report file {path}: {error}") from error
    return load_report_bytes(raw, source_name=str(path))


def build_send_plan(report: dict[str, Any]) -> SendPlan:
    """Create a fully validated, ordered send plan without opening a connection."""

    message_id, canonical_payload = canonical_report_bytes(report)
    frames = tuple(encode_report(report))
    if not frames:
        raise SenderConfigurationError("the frozen codec produced no frames")
    for expected_index, raw_frame in enumerate(frames):
        frame = decode_frame(raw_frame)
        if frame.message_id != message_id or frame.fragment_index != expected_index:
            raise SenderConfigurationError("the frozen codec produced an inconsistent frame set")
        if len(raw_frame) > MAX_APPLICATION_PAYLOAD:
            raise SenderConfigurationError("the frozen codec exceeded the Meshtastic byte budget")
    return SendPlan(
        message_id=message_id,
        canonical_payload_size=len(canonical_payload),
        frames=frames,
    )


def validate_options(options: SenderOptions) -> None:
    if not options.host or len(options.host) > 255 or any(char.isspace() for char in options.host):
        raise SenderConfigurationError("host must be 1..255 non-whitespace characters")
    if not 1 <= options.port <= 65_535:
        raise SenderConfigurationError("port must be between 1 and 65535")
    if options.destination != "^all" and _NODE_ID.fullmatch(options.destination) is None:
        raise SenderConfigurationError("destination must be '^all' or a node ID like '!1a2b3c4d'")
    if not 0 <= options.channel_index <= 7:
        raise SenderConfigurationError("channel index must be between 0 and 7")
    if not 1 <= options.hop_limit <= 7:
        raise SenderConfigurationError("hop limit must be between 1 and 7")
    if not 0 <= options.interval_seconds <= MAX_INTERVAL_SECONDS:
        raise SenderConfigurationError(
            f"frame interval must be between 0 and {MAX_INTERVAL_SECONDS:g} seconds"
        )
    if not 1 <= options.connect_timeout_seconds <= MAX_CONNECT_TIMEOUT_SECONDS:
        raise SenderConfigurationError(
            f"connect timeout must be between 1 and {MAX_CONNECT_TIMEOUT_SECONDS} seconds"
        )


def _validate_send_plan(plan: SendPlan) -> None:
    """Reject manually constructed plans that do not match the frozen codec."""

    if not plan.frames:
        raise SenderConfigurationError("send plan must contain at least one frame")

    expected_count = len(plan.frames)
    expected_digest: bytes | None = None
    for expected_index, raw_frame in enumerate(plan.frames):
        try:
            frame = decode_frame(raw_frame)
        except ProtocolError as error:
            raise SenderConfigurationError(
                f"send plan fragment {expected_index + 1} is invalid"
            ) from error
        if frame.message_id != plan.message_id:
            raise SenderConfigurationError("send plan contains a different message ID")
        if frame.fragment_index != expected_index or frame.fragment_count != expected_count:
            raise SenderConfigurationError("send plan fragments are missing or out of order")
        if frame.total_length != plan.canonical_payload_size:
            raise SenderConfigurationError("send plan payload length is inconsistent")
        if expected_digest is None:
            expected_digest = frame.payload_digest
        elif not hmac.compare_digest(frame.payload_digest, expected_digest):
            raise SenderConfigurationError("send plan payload digest is inconsistent")


def _meshtastic_interface_factory(
    host: str, port: int, timeout_seconds: int
) -> MeshtasticInterface:
    try:
        installed_version = importlib.metadata.version("meshtastic")
    except importlib.metadata.PackageNotFoundError as error:
        raise SenderDependencyError(
            'Meshtastic client is not installed; run: python -m pip install -e ".[sender]"'
        ) from error
    if installed_version != MESHTASTIC_PYTHON_VERSION:
        raise SenderDependencyError(
            f"Meshtastic client {MESHTASTIC_PYTHON_VERSION} is required; found {installed_version}"
        )
    try:
        from meshtastic.tcp_interface import TCPInterface
    except ImportError as error:
        raise SenderDependencyError(
            "the installed Meshtastic TCP interface cannot be imported"
        ) from error
    try:
        return TCPInterface(
            hostname=host,
            portNumber=port,
            timeout=timeout_seconds,
        )
    except Exception as error:
        raise SenderTransportError(
            f"cannot connect to Meshtastic TCP node {host}:{port}"
        ) from error


def send_plan(
    plan: SendPlan,
    options: SenderOptions,
    *,
    interface_factory: InterfaceFactory = _meshtastic_interface_factory,
    sleeper: Sleeper = time.sleep,
) -> int:
    """Send every frame in order and always close an opened interface."""

    _validate_send_plan(plan)
    validate_options(options)
    try:
        interface = interface_factory(
            options.host,
            options.port,
            options.connect_timeout_seconds,
        )
    except SenderError:
        raise
    except Exception as error:
        raise SenderTransportError(
            f"cannot connect to Meshtastic TCP node {options.host}:{options.port}"
        ) from error

    send_error: Exception | None = None
    try:
        for index, frame in enumerate(plan.frames):
            try:
                interface.sendData(
                    frame,
                    options.destination,
                    portNum=APPLICATION_PORT,
                    wantAck=False,
                    channelIndex=options.channel_index,
                    hopLimit=options.hop_limit,
                )
            except Exception as error:
                raise SenderTransportError(
                    f"failed to send fragment {index + 1} of {plan.frame_count}"
                ) from error
            if index + 1 < plan.frame_count and options.interval_seconds > 0:
                sleeper(options.interval_seconds)
    except Exception as error:
        send_error = error
        raise
    finally:
        try:
            interface.close()
        except Exception as error:
            if send_error is None:
                raise SenderTransportError(
                    "failed to close the Meshtastic TCP interface"
                ) from error
    return plan.frame_count


def _bounded_int(name: str, minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value, 10)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from error
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    return parse


def _interval_ms(value: str) -> float:
    milliseconds = _bounded_int("interval-ms", 0, int(MAX_INTERVAL_SECONDS * 1000))(value)
    return milliseconds / 1000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protidhoni-lora-send",
        description="Send one already signed Protidhoni report through Meshtastic PRIVATE_APP frames.",
    )
    parser.add_argument("report", help="UTF-8 report JSON path, or '-' for standard input")
    parser.add_argument("--host", default=DEFAULT_TCP_HOST)
    parser.add_argument(
        "--port",
        type=_bounded_int("port", 1, 65_535),
        default=DEFAULT_TCP_PORT,
    )
    parser.add_argument("--destination", default="^all")
    parser.add_argument(
        "--channel-index",
        type=_bounded_int("channel-index", 0, 7),
        default=DEFAULT_CHANNEL_INDEX,
    )
    parser.add_argument(
        "--hop-limit",
        type=_bounded_int("hop-limit", 1, 7),
        default=DEFAULT_HOP_LIMIT,
    )
    parser.add_argument(
        "--interval-ms",
        type=_interval_ms,
        default=DEFAULT_INTERVAL_SECONDS,
        help="delay between frames in milliseconds (default: 1000)",
    )
    parser.add_argument(
        "--connect-timeout",
        type=_bounded_int("connect-timeout", 1, MAX_CONNECT_TIMEOUT_SECONDS),
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        help="TCP/configuration timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and summarize without importing Meshtastic or opening TCP",
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    interface_factory: InterfaceFactory = _meshtastic_interface_factory,
    sleeper: Sleeper = time.sleep,
) -> int:
    args = _parser().parse_args(argv)
    options = SenderOptions(
        host=args.host,
        port=args.port,
        destination=args.destination,
        channel_index=args.channel_index,
        hop_limit=args.hop_limit,
        interval_seconds=args.interval_ms,
        connect_timeout_seconds=args.connect_timeout,
    )
    try:
        validate_options(options)
        report = read_report(args.report, stdin=stdin)
        plan = build_send_plan(report)
        summary = (
            f"message_id={plan.message_id} canonical_bytes={plan.canonical_payload_size} "
            f"frames={plan.frame_count}"
        )
        if args.dry_run:
            print(f"validated {summary}; dry-run, no packets sent", file=stdout)
            return 0
        sent = send_plan(
            plan,
            options,
            interface_factory=interface_factory,
            sleeper=sleeper,
        )
        print(f"sent {summary} packets_sent={sent}", file=stdout)
        return 0
    except (ProtocolError, SenderError) as error:
        print(f"error: {error}", file=stderr)
        return 2


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
