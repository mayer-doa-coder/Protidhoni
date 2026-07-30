"""Provider-specific webhook authentication primitives.

The gateway endpoints accept crisis reports from an external telco provider, so
they are the one place in this backend where an unauthenticated caller could
inject fabricated reports directly into the responder dashboard. Every request
must therefore prove it came from the configured provider before it is parsed.

SMS uses Twilio's documented request signature:

    signature = base64(HMAC-SHA1(auth_token, url + concat(sorted(k + v))))

The offline USSD simulator is not represented as Twilio or as a real telco. It
uses a separate HMAC-SHA256 signature over the callback URL and exact form body.
A live USSD aggregator requires a small adapter for that provider's documented
fields and authentication scheme.
"""

from __future__ import annotations

import base64
import hmac
from collections.abc import Mapping
from hashlib import sha1, sha256
from urllib.parse import urlsplit, urlunsplit

TWILIO_SIGNATURE_HEADER = "X-Twilio-Signature"
SIMULATOR_SIGNATURE_HEADER = "X-Protidhoni-Gateway-Signature"


class WebhookAuthError(Exception):
    """A provider callback could not be authenticated.

    ``status_code`` distinguishes a server misconfiguration (503, our fault,
    the operator must set the secret) from a rejected caller (401, their fault).
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def expected_twilio_signature(*, url: str, params: Mapping[str, str], auth_token: str) -> str:
    """Compute the signature the provider should have sent for this request.

    Params are concatenated in sorted key order with no separators, appended to
    the full request URL including any query string — this exact serialization
    is what the provider signs, so any deviation silently rejects real traffic.
    """
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_twilio_signature(
    *,
    url: str,
    params: Mapping[str, str],
    presented_signature: str | None,
    auth_token: str | None,
) -> None:
    """Raise WebhookAuthError unless this request is a genuine provider callback."""
    if auth_token is None:
        raise WebhookAuthError(
            "The SMS/USSD gateway is not securely configured on this instance.",
            status_code=503,
        )

    expected = expected_twilio_signature(url=url, params=params, auth_token=auth_token)
    if presented_signature is None or not hmac.compare_digest(presented_signature, expected):
        raise WebhookAuthError("Invalid provider webhook signature.", status_code=401)


def expected_simulator_signature(*, url: str, body: bytes, auth_token: str) -> str:
    """Return the offline USSD simulator signature.

    Prefixing a version and binding both URL and exact bytes makes the format
    unambiguous, endpoint-bound, and safe to evolve without claiming vendor
    compatibility.
    """
    signed = b"v1\n" + url.encode("utf-8") + b"\n" + body
    digest = hmac.new(auth_token.encode("utf-8"), signed, sha256).digest()
    return "v1=" + base64.b64encode(digest).decode("ascii")


def verify_simulator_signature(
    *,
    url: str,
    body: bytes,
    presented_signature: str | None,
    auth_token: str | None,
) -> None:
    """Authenticate the explicitly local/offline USSD simulator adapter."""
    if auth_token is None:
        raise WebhookAuthError(
            "The USSD simulator adapter is not securely configured on this instance.",
            status_code=503,
        )
    expected = expected_simulator_signature(url=url, body=body, auth_token=auth_token)
    if presented_signature is None or not hmac.compare_digest(presented_signature, expected):
        raise WebhookAuthError("Invalid USSD adapter signature.", status_code=401)


def resolve_signed_url(*, request_url: str, public_base_url: str | None) -> str:
    """Return the URL the provider actually signed.

    Behind a TLS-terminating proxy (Render, Fly.io, nginx in compose) the URL
    this process observes can be ``http://`` on an internal hostname while the
    provider signed the public ``https://`` origin. Verifying against the
    unadjusted inbound URL would then reject every genuine callback, so
    deployments behind a proxy set PROTIDHONI_GATEWAY_PUBLIC_BASE_URL and the
    origin is swapped back before the digest is computed.
    """
    if not public_base_url:
        return request_url

    inbound = urlsplit(request_url)
    public = urlsplit(public_base_url.rstrip("/"))
    path = public.path + inbound.path
    return urlunsplit((public.scheme, public.netloc, path, inbound.query, ""))
