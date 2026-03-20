"""Shared helper functions for the Pulumi program."""

import os
from typing import Any


def required_env(name: str) -> str:
    """Return the value of a required environment variable, or raise."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def int_env(name: str, default: int) -> int:
    """Return an integer environment variable, or *default* if unset."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {value}") from exc


def service_external_ip(status: Any) -> str | None:
    """Extract the first external IP from a Kubernetes Service status."""
    if status is None:
        return None

    if isinstance(status, dict):
        ingress = status.get("load_balancer", {}).get("ingress", [])
        if ingress:
            first = ingress[0]
            if isinstance(first, dict):
                return first.get("ip")
        return None

    load_balancer = getattr(status, "load_balancer", None)
    if not load_balancer:
        return None
    ingress = getattr(load_balancer, "ingress", None) or []
    if not ingress:
        return None
    return getattr(ingress[0], "ip", None)
