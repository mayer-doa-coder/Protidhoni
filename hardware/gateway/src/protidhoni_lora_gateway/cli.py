"""Command-line entry point for the simulated LoRa gateway."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections.abc import Sequence
from dataclasses import replace

from .backend import BackendClient
from .config import GatewayConfigurationError, GatewaySettings
from .processor import GatewayProcessor
from .receiver import MeshtasticReceiver, ReceiverError
from .runtime import FrameWorker, WorkerError

logger = logging.getLogger(__name__)


def _parser(settings: GatewaySettings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protidhoni-lora-gateway",
        description="Bridge Protidhoni PRIVATE_APP frames to the existing POST /reports API.",
    )
    parser.add_argument("--meshtastic-host", default=settings.meshtastic_host)
    parser.add_argument("--meshtastic-port", type=int, default=settings.meshtastic_port)
    parser.add_argument("--backend-url", default=settings.backend_url)
    parser.add_argument("--connect-timeout", type=int, default=settings.connect_timeout_seconds)
    parser.add_argument("--http-timeout", type=float, default=settings.http_timeout_seconds)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    try:
        base_settings = GatewaySettings.from_environment()
        args = _parser(base_settings).parse_args(argv)
        settings = replace(
            base_settings,
            meshtastic_host=args.meshtastic_host,
            meshtastic_port=args.meshtastic_port,
            backend_url=args.backend_url,
            connect_timeout_seconds=args.connect_timeout,
            http_timeout_seconds=args.http_timeout,
        )
    except GatewayConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = threading.Event()
    backend = BackendClient(
        base_url=settings.backend_url,
        timeout_seconds=settings.http_timeout_seconds,
        attempts=settings.backend_attempts,
        retry_delay_seconds=settings.backend_retry_delay_seconds,
    )
    processor = GatewayProcessor(
        backend,
        pending_capacity=settings.pending_capacity,
        pending_retry_seconds=settings.pending_retry_seconds,
        pending_ttl_seconds=settings.pending_ttl_seconds,
    )
    worker = FrameWorker(
        processor,
        capacity=settings.frame_queue_capacity,
        stop_event=stop_event,
    )
    receiver = MeshtasticReceiver(
        host=settings.meshtastic_host,
        port=settings.meshtastic_port,
        connect_timeout_seconds=settings.connect_timeout_seconds,
    )

    exit_code = 0
    worker.start()
    try:
        receiver.run(worker.submit, stop_event=stop_event, healthcheck=worker.raise_if_failed)
        worker.raise_if_failed()
    except KeyboardInterrupt:
        logger.info("Gateway shutdown requested")
    except (ReceiverError, WorkerError) as error:
        logger.error("Gateway stopped: %s", error)
        exit_code = 1
    finally:
        try:
            worker.stop()
        except WorkerError as error:
            logger.error("Gateway worker shutdown failed: %s", error)
            exit_code = 1
        backend.close()

    metrics = processor.metrics
    logger.info(
        "Gateway stopped frames=%s rejected_frames=%s accepted_reports=%s "
        "duplicate_reports=%s rejected_reports=%s pending=%s",
        metrics.frames_received,
        metrics.frames_rejected,
        metrics.reports_accepted,
        metrics.reports_duplicate,
        metrics.reports_rejected,
        processor.pending_count,
    )
    return exit_code


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
