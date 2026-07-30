"""Authenticated SMS and simulated-USSD ingress for feature phones.

Twilio SMS and the offline USSD simulator are separate adapters: they have
different request-authentication schemes and different response formats.  Both
normalize their input into a ``ReportDraft`` and then use the same signed-report
ingestion service as ``POST /reports``.

Provider-supplied phone metadata is normalized, reduced to a peppered HMAC for
in-memory rate limiting, and discarded.  It is never copied into a report.  A
phone number deliberately typed into the user's report text remains user
content and is retained like any other report text.
"""

from __future__ import annotations

import hmac
import re
import uuid
from hashlib import sha256
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from psycopg_pool import AsyncConnectionPool

from . import gateway_ussd
from .config import get_settings
from .gateway_identity import GatewayIdentityError, ReportDraft, build_signed_report
from .gateway_sms import SmsParseError, parse_sms_body
from .gateway_webhook import (
    SIMULATOR_SIGNATURE_HEADER,
    TWILIO_SIGNATURE_HEADER,
    WebhookAuthError,
    resolve_signed_url,
    verify_simulator_signature,
    verify_twilio_signature,
)
from .ingestion import IngestionDecision, ingest_signed_report
from .models import Report
from .ratelimit import SenderRateLimiter
from .routes import get_db_pool

router = APIRouter(prefix="/gateway", tags=["gateway"])

_phone_limiter = SenderRateLimiter(max_reports_per_minute=5)
_GATEWAY_UUID_NAMESPACE = uuid.UUID("8f1d6c2e-4a7b-4f52-9c3d-0b6a5e2f7c14")
_MAX_FORM_BODY_BYTES = 8 * 1024
_MAX_FORM_FIELDS = 32
_E164_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_TWILIO_MESSAGE_SID_RE = re.compile(r"^SM[0-9A-Fa-f]{32}$")
_USSD_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def _read_form(request: Request) -> tuple[bytes, dict[str, str]]:
    """Read one small, unambiguous form body.

    Strict content type, size, UTF-8, field count, and unique keys keep webhook
    signature verification and parsing in agreement and bound memory use before
    any user-controlled report text is processed.
    """
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Expected a form-encoded webhook body.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from error
        if declared_length < 0 or declared_length > _MAX_FORM_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook body is too large.")

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_FORM_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook body is too large.")
        chunks.append(chunk)
    raw_body = b"".join(chunks)

    try:
        encoded_form = raw_body.decode("utf-8", errors="strict")
        pairs = parse_qsl(
            encoded_form,
            keep_blank_values=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=_MAX_FORM_FIELDS,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="Malformed webhook form body.") from error

    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise HTTPException(
            status_code=400, detail="Duplicate webhook form fields are not allowed."
        )
    return raw_body, dict(pairs)


def _signed_url(request: Request) -> str:
    return resolve_signed_url(
        request_url=str(request.url),
        public_base_url=get_settings().gateway_public_base_url,
    )


def _authenticate_twilio_sms(request: Request, params: dict[str, str]) -> None:
    try:
        verify_twilio_signature(
            url=_signed_url(request),
            params=params,
            presented_signature=request.headers.get(TWILIO_SIGNATURE_HEADER),
            auth_token=get_settings().configured_gateway_webhook_token(),
        )
    except WebhookAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


def _authenticate_simulated_ussd(request: Request, raw_body: bytes) -> None:
    try:
        verify_simulator_signature(
            url=_signed_url(request),
            body=raw_body,
            presented_signature=request.headers.get(SIMULATOR_SIGNATURE_HEADER),
            auth_token=get_settings().configured_gateway_ussd_webhook_token(),
        )
    except WebhookAuthError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


def _normalized_phone(value: str) -> str:
    """Require one canonical E.164 representation before applying a quota."""
    if not _E164_PHONE_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail="Provider phone number must use E.164 format.")
    return value


def _phone_pseudonym(phone_number: str) -> str:
    pepper = get_settings().configured_gateway_phone_pepper()
    if pepper is None:
        raise HTTPException(
            status_code=503,
            detail="The SMS/USSD gateway is not securely configured on this instance.",
        )
    return hmac.new(pepper.encode(), phone_number.encode(), sha256).hexdigest()


def _gateway_message_id(channel: str, provider_id: str) -> str:
    """Namespace provider and channel so unrelated ids cannot collide."""
    return str(uuid.uuid5(_GATEWAY_UUID_NAMESPACE, f"{channel}:{provider_id}"))


async def _sign_and_ingest(
    draft: ReportDraft,
    *,
    message_id: str,
    phone_rate_limit_key: str,
    pool: AsyncConnectionPool,
) -> IngestionDecision:
    try:
        report = Report.model_validate(build_signed_report(draft, message_id=message_id))
    except GatewayIdentityError as error:
        raise HTTPException(
            status_code=503,
            detail="The SMS/USSD gateway is not securely configured on this instance.",
        ) from error

    decision = await ingest_signed_report(
        pool,
        report,
        limiter=_phone_limiter,
        rate_limit_key=phone_rate_limit_key,
        check_duplicate_first=True,
    )
    if decision.rejection_reason == "rate_limited":
        raise HTTPException(status_code=429, detail="Too many messages from this sender.")
    if decision.rejection_reason == "invalid_signature":  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="The gateway produced an unverifiable report.")
    return decision


@router.post("/sms", response_class=Response)
async def receive_sms(
    request: Request,
    pool: AsyncConnectionPool = Depends(get_db_pool),
) -> Response:
    """Accept an authenticated Twilio SMS and return an empty TwiML response."""
    _, params = await _read_form(request)
    _authenticate_twilio_sms(request, params)

    provider_message_id = params.get("MessageSid") or params.get("SmsSid") or ""
    if not _TWILIO_MESSAGE_SID_RE.fullmatch(provider_message_id):
        raise HTTPException(status_code=400, detail="Missing or invalid Twilio MessageSid.")
    phone = _normalized_phone(params.get("From", ""))

    try:
        draft = parse_sms_body(params.get("Body", ""))
    except SmsParseError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    message_id = _gateway_message_id("twilio:sms", provider_message_id)
    decision = await _sign_and_ingest(
        draft,
        message_id=message_id,
        phone_rate_limit_key=_phone_pseudonym(phone),
        pool=pool,
    )
    return Response(
        content="<Response/>",
        media_type="application/xml",
        headers={
            "X-Protidhoni-Message-Id": message_id,
            "X-Protidhoni-Ingest-Outcome": decision.outcome,
        },
    )


@router.post("/ussd", response_class=PlainTextResponse)
async def receive_ussd(
    request: Request,
    pool: AsyncConnectionPool = Depends(get_db_pool),
) -> PlainTextResponse:
    """Advance the authenticated offline USSD simulator's stateless menu."""
    raw_body, params = await _read_form(request)
    _authenticate_simulated_ussd(request, raw_body)

    session_id = params.get("sessionId", "")
    if not _USSD_SESSION_ID_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="Missing or invalid USSD session id.")
    phone = _normalized_phone(params.get("phoneNumber", ""))

    menu_response = gateway_ussd.advance_session(params.get("text", ""))
    if menu_response.draft is None:
        return PlainTextResponse(menu_response.body)

    message_id = _gateway_message_id("simulator:ussd", session_id)
    decision = await _sign_and_ingest(
        menu_response.draft,
        message_id=message_id,
        phone_rate_limit_key=_phone_pseudonym(phone),
        pool=pool,
    )
    return PlainTextResponse(
        menu_response.body,
        headers={
            "X-Protidhoni-Message-Id": message_id,
            "X-Protidhoni-Ingest-Outcome": decision.outcome,
        },
    )
