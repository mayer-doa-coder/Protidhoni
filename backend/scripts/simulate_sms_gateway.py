"""Exercise the SMS and simulated-USSD gateways without a telco account.

SMS callbacks use Twilio's documented form signature. USSD is explicitly a
local simulator with a separate HMAC-SHA256 adapter; it does not pretend to be
a live telco provider. Authentication, parsing, signing, and persistence are
not mocked or bypassed inside the backend.

    python .\\backend\\scripts\\simulate_sms_gateway.py sms
    python .\\backend\\scripts\\simulate_sms_gateway.py ussd
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from protidhoni_api.gateway_webhook import (
    SIMULATOR_SIGNATURE_HEADER,
    TWILIO_SIGNATURE_HEADER,
    expected_simulator_signature,
    expected_twilio_signature,
)

DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_FROM = "+8801700000000"
DEFAULT_SERVICE_CODE = "*789#"
DEFAULT_USSD_KEYPRESSES = ("1", "1", "4", "4")


def _configured_token(process_name: str, dotenv_name: str) -> str:
    """Read a token from the process first, then the ignored root ``.env``.

    Values are never printed. The process override is useful for a deployed
    simulator; the file fallback keeps the local demo to one command.
    """
    process_value = os.environ.get(process_name, "")
    if process_value:
        return process_value

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return ""
    prefix = dotenv_name + "="
    for line in reversed(env_path.read_text(encoding="utf-8").splitlines()):
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _post(
    url: str,
    params: dict[str, str],
    *,
    signature_header: str,
    signature: str,
) -> tuple[int, str, dict[str, str]]:
    body = urlencode(params).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            signature_header: signature,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - explicit demo URL
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, response.read().decode("utf-8"), headers
    except HTTPError as error:
        headers = {key.lower(): value for key, value in error.headers.items()}
        return error.code, error.read().decode("utf-8"), headers


def _post_twilio_sms(
    url: str, params: dict[str, str], auth_token: str
) -> tuple[int, str, dict[str, str]]:
    return _post(
        url,
        params,
        signature_header=TWILIO_SIGNATURE_HEADER,
        signature=expected_twilio_signature(url=url, params=params, auth_token=auth_token),
    )


def _post_simulated_ussd(
    url: str, params: dict[str, str], auth_token: str
) -> tuple[int, str, dict[str, str]]:
    body = urlencode(params).encode("utf-8")
    return _post(
        url,
        params,
        signature_header=SIMULATOR_SIGNATURE_HEADER,
        signature=expected_simulator_signature(url=url, body=body, auth_token=auth_token),
    )


def simulate_sms(api_base: str, auth_token: str, *, body: str, from_number: str) -> int:
    params = {
        "MessageSid": f"SM{uuid.uuid4().hex}",
        "From": from_number,
        "To": DEFAULT_SERVICE_CODE,
        "Body": body,
    }
    url = f"{api_base}/gateway/sms"
    status, response_body, headers = _post_twilio_sms(url, params, auth_token)
    print(f"SMS -> HTTP {status}: {response_body}")
    if status != 200 or not response_body.startswith("<Response"):
        return 1

    status, replay_body, replay_headers = _post_twilio_sms(url, params, auth_token)
    print(f"replay -> HTTP {status}: {replay_body}")
    if (
        status != 200
        or headers.get("x-protidhoni-message-id") != replay_headers.get("x-protidhoni-message-id")
        or replay_headers.get("x-protidhoni-ingest-outcome") != "duplicate"
    ):
        print("FAIL: replaying the same MessageSid did not deduplicate.", file=sys.stderr)
        return 1
    return 0


def simulate_ussd(api_base: str, auth_token: str, *, from_number: str) -> int:
    session_id = f"US{uuid.uuid4().hex}"
    keypresses: list[str] = []

    for step in range(len(DEFAULT_USSD_KEYPRESSES) + 1):
        params = {
            "sessionId": session_id,
            "serviceCode": DEFAULT_SERVICE_CODE,
            "phoneNumber": from_number,
            "text": "*".join(keypresses),
        }
        url = f"{api_base}/gateway/ussd"
        status, body, _ = _post_simulated_ussd(url, params, auth_token)
        print(f"USSD step {step} -> HTTP {status}")
        print("  " + body.replace("\n", "\n  "))
        if status != 200:
            return 1
        if body.startswith("END "):
            return 0 if step == len(DEFAULT_USSD_KEYPRESSES) else 1
        keypresses.append(DEFAULT_USSD_KEYPRESSES[step])

    print("FAIL: the USSD session never terminated.", file=sys.stderr)
    return 1


def main() -> int:
    # Windows may select a legacy CP-1252 console even though USSD responses
    # intentionally contain Bangla. Keep the demo output faithful instead of
    # crashing after an otherwise successful callback.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--from-number", default=DEFAULT_FROM)
    subparsers = parser.add_subparsers(dest="channel", required=True)

    sms_parser = subparsers.add_parser("sms", help="Send one simulated inbound SMS.")
    sms_parser.add_argument(
        "--body",
        default="SOS trapped on roof 23.8103,90.4125 need rescue 4 people",
    )
    subparsers.add_parser("ussd", help="Walk one full simulated USSD menu session.")

    args = parser.parse_args()
    sms_token = _configured_token("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", "GATEWAY_WEBHOOK_TOKEN")
    ussd_token = _configured_token(
        "PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN", "GATEWAY_USSD_WEBHOOK_TOKEN"
    )
    selected_token = sms_token if args.channel == "sms" else ussd_token
    variable = (
        "PROTIDHONI_GATEWAY_WEBHOOK_TOKEN"
        if args.channel == "sms"
        else "PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN"
    )
    if len(selected_token) < 32:
        print(
            f"Set {variable} to the same 32+ character value used by the backend.",
            file=sys.stderr,
        )
        return 2

    api_base = args.api_base.rstrip("/")
    if args.channel == "sms":
        return simulate_sms(api_base, sms_token, body=args.body, from_number=args.from_number)
    return simulate_ussd(api_base, ussd_token, from_number=args.from_number)


if __name__ == "__main__":
    raise SystemExit(main())
