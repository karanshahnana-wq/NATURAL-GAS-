"""Small, testable Kotak Neo options-chain envelope validator.

This validates the outer response schema only. Individual field mapping remains
handled by the richer endpoint parser and must be checked against live broker data.
"""
from typing import Any


def extract_option_sides(response: Any) -> tuple[dict, list, list, dict]:
    if not isinstance(response, dict):
        return {}, [], [], {"valid": False, "reason": "response_not_object"}
    if response.get("error") or response.get("errors"):
        return {}, [], [], {"valid": False, "reason": "broker_reported_error"}
    data = response.get("data", response)
    if not isinstance(data, dict):
        return {}, [], [], {"valid": False, "reason": "data_not_object"}
    calls = data.get("call", [])
    puts = data.get("put", [])
    if not isinstance(calls, list) or not isinstance(puts, list):
        return data, [], [], {"valid": False, "reason": "call_or_put_not_list"}
    valid = bool(calls or puts)
    return data, calls, puts, {
        "valid": valid,
        "reason": "ok" if valid else "empty_call_put_sides",
        "data_keys": sorted(str(k) for k in data.keys()),
        "call_rows": len(calls),
        "put_rows": len(puts),
        "call_sample_keys": sorted(str(k) for k in calls[0].keys()) if calls and isinstance(calls[0], dict) else [],
        "put_sample_keys": sorted(str(k) for k in puts[0].keys()) if puts and isinstance(puts[0], dict) else [],
    }
