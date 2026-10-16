"""Secure Kotak Neo connection helpers for MCX Natural Gas Radar.

Credentials belong only in the hosting provider's environment variables.
This module never returns or logs credential values.
"""
from __future__ import annotations

import os
import logging
from typing import Any

REQUIRED_ENV = (
    "NEO_CONSUMER_KEY",
    "NEO_MOBILE_NUMBER",
    "NEO_UCC",
    "NEO_MPIN",
    "NEO_TOTP_SECRET",
)


def _value(key: str, legacy_key: str | None = None) -> str:
    """Read the preferred environment key, with a backwards-compatible alias."""
    value = os.getenv(key, "").strip()
    if value:
        return value
    return os.getenv(legacy_key, "").strip() if legacy_key else ""


def connection_status() -> dict[str, Any]:
    """Return safe readiness metadata; never disclose the actual secrets."""
    present = {
        "NEO_CONSUMER_KEY": bool(_value("NEO_CONSUMER_KEY")),
        "NEO_MOBILE_NUMBER": bool(_value("NEO_MOBILE_NUMBER")),
        "NEO_UCC": bool(_value("NEO_UCC")),
        "NEO_MPIN": bool(_value("NEO_MPIN", "MPIN")),
        "NEO_TOTP_SECRET": bool(_value("NEO_TOTP_SECRET")),
    }
    ready = all(present.values())
    return {
        "configured": ready,
        "mode": "credentials_ready" if ready else "not_configured",
        "missing": [key for key, exists in present.items() if not exists],
        "sdk_available": _sdk_available(),
        "message": (
            "Credentials are present. Authentication and MCX instrument verification still need to be tested."
            if ready
            else "Add the missing values as private Render environment variables. Never paste credentials into chat."
        ),
    }


def _mobile_number() -> str:
    """Format an Indian 10-digit mobile number as required by the current SDK (+91...)."""
    raw = _value("NEO_MOBILE_NUMBER")
    compact = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    digits = "".join(ch for ch in compact if ch.isdigit())
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if compact.startswith("+") and len(digits) >= 10:
        return "+" + digits
    raise RuntimeError("NEO_MOBILE_NUMBER must be a valid registered mobile number; use +91 followed by the 10-digit Indian number.")


def _totp_secret() -> str:
    """Normalize a copied Base32 setup key or otpauth:// URI without exposing it."""
    import base64
    from urllib.parse import parse_qs, urlparse

    raw = _value("NEO_TOTP_SECRET")
    if raw.lower().startswith("otpauth://"):
        parsed = urlparse(raw)
        raw = parse_qs(parsed.query).get("secret", [""])[0]
    secret = "".join(raw.split()).replace("-", "").upper()
    if not secret:
        raise RuntimeError("NEO_TOTP_SECRET is empty. Save the TOTP setup key from Kotak's API TOTP registration.")
    try:
        base64.b32decode(secret + ("=" * ((8 - len(secret) % 8) % 8)), casefold=True)
    except Exception:
        raise RuntimeError("NEO_TOTP_SECRET is not a valid Base32 setup key. Save the authenticator setup key, not a six-digit code.")
    return secret


def _has_api_error(response: Any) -> bool:
    """Detect SDK responses that contain an API error even if no exception was raised."""
    if not isinstance(response, dict):
        return False
    return bool(response.get("error") or response.get("errors") or response.get("status") == "error")


def _sdk_available() -> bool:
    try:
        import neo_api_client  # noqa: F401
        import pyotp  # noqa: F401
        return True
    except ImportError:
        return False


def create_authenticated_client() -> Any:
    """Authenticate on demand without allowing SDK request bodies into hosted logs."""
    # The SDK logs login request payloads at ERROR level in some versions. App routes
    # return sanitized diagnostics, so suppress its payload logger to protect account
    # identifiers, authentication metadata, and request bodies in Render logs.
    for logger_name in (
        "neo_api_client", "neo_api_client.rest", "neo_api_client.websocket",
        "neo_api_client.rest_client",
    ):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
    status = connection_status()
    if not status["configured"]:
        raise RuntimeError("Kotak Neo credentials are not fully configured.")
    if not status["sdk_available"]:
        raise RuntimeError("Kotak Neo SDK or TOTP dependency is unavailable.")

    from neo_api_client import NeoAPI
    import pyotp

    client = NeoAPI(
        consumer_key=_value("NEO_CONSUMER_KEY"),
        environment=os.getenv("NEO_ENVIRONMENT", "prod"),
    )
    mobile = _mobile_number()
    ucc = _value("NEO_UCC")
    # Normalize spaces/case/otpauth URI so pasted setup keys work reliably.
    secret = _totp_secret()
    totp = pyotp.TOTP(secret).now()

    login_response = client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)
    if _has_api_error(login_response):
        raise RuntimeError("Kotak rejected the TOTP login request. Verify registered mobile number and API credentials.")
    validate_response = client.totp_validate(mpin=_value("NEO_MPIN", "MPIN"))
    if _has_api_error(validate_response):
        raise RuntimeError("Kotak rejected the MPIN validation request. Verify MPIN and TOTP registration.")
    return client
