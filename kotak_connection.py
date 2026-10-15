"""Secure Kotak Neo connection helpers for MCX Natural Gas Radar.

Credentials belong only in the hosting provider's environment variables.
This module never returns or logs credential values.
"""
from __future__ import annotations

import os
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


def _sdk_available() -> bool:
    try:
        import neo_api_client  # noqa: F401
        import pyotp  # noqa: F401
        return True
    except ImportError:
        return False


def create_authenticated_client() -> Any:
    """Authenticate on demand; callers must not expose SDK errors containing secrets."""
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
    mobile = _value("NEO_MOBILE_NUMBER")
    ucc = _value("NEO_UCC")
    totp = pyotp.TOTP(_value("NEO_TOTP_SECRET")).now()

    client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)
    client.totp_validate(mpin=_value("NEO_MPIN", "MPIN"))
    return client
