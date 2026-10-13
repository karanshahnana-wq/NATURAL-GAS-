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


def connection_status() -> dict[str, Any]:
    """Return safe readiness metadata; never disclose the actual secrets."""
    present = {key: bool(os.getenv(key, "").strip()) for key in REQUIRED_ENV}
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
        consumer_key=os.environ["NEO_CONSUMER_KEY"],
        environment=os.getenv("NEO_ENVIRONMENT", "prod"),
    )
    mobile = os.environ["NEO_MOBILE_NUMBER"]
    ucc = os.environ["NEO_UCC"]
    totp = pyotp.TOTP(os.environ["NEO_TOTP_SECRET"]).now()

    client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)
    client.totp_validate(mpin=os.environ["NEO_MPIN"])
    return client
