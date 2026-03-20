"""Unit tests for helper functions."""

import os
from types import SimpleNamespace

import pytest

from components.helpers import required_env, int_env, service_external_ip


# ── required_env ──────────────────────────────────────────────────────────────

def test_required_env_returns_value(monkeypatch):
    """Should return the env var value when set."""
    monkeypatch.setenv("TEST_VAR", "hello")
    assert required_env("TEST_VAR") == "hello"


def test_required_env_raises_when_missing(monkeypatch):
    """Should raise ValueError when the env var is not set."""
    monkeypatch.delenv("TEST_VAR", raising=False)
    with pytest.raises(ValueError, match="Missing required environment variable: TEST_VAR"):
        required_env("TEST_VAR")


def test_required_env_raises_when_empty(monkeypatch):
    """Should raise ValueError when the env var is empty string."""
    monkeypatch.setenv("TEST_VAR", "")
    with pytest.raises(ValueError, match="Missing required environment variable: TEST_VAR"):
        required_env("TEST_VAR")


# ── int_env ───────────────────────────────────────────────────────────────────

def test_int_env_returns_parsed_int(monkeypatch):
    """Should parse and return the integer value."""
    monkeypatch.setenv("TEST_INT", "42")
    assert int_env("TEST_INT", 0) == 42


def test_int_env_returns_default_when_missing(monkeypatch):
    """Should return default when the env var is not set."""
    monkeypatch.delenv("TEST_INT", raising=False)
    assert int_env("TEST_INT", 99) == 99


def test_int_env_raises_on_non_integer(monkeypatch):
    """Should raise ValueError when the value is not an integer."""
    monkeypatch.setenv("TEST_INT", "abc")
    with pytest.raises(ValueError, match="TEST_INT must be an integer, got: abc"):
        int_env("TEST_INT", 0)


# ── service_external_ip ──────────────────────────────────────────────────────

def test_external_ip_none_status():
    """Should return None when status is None."""
    assert service_external_ip(None) is None


def test_external_ip_dict_with_ip():
    """Should extract IP from a dict-style status."""
    status = {
        "load_balancer": {
            "ingress": [{"ip": "1.2.3.4"}],
        },
    }
    assert service_external_ip(status) == "1.2.3.4"


def test_external_ip_dict_empty_ingress():
    """Should return None when ingress list is empty."""
    status = {"load_balancer": {"ingress": []}}
    assert service_external_ip(status) is None


def test_external_ip_dict_no_load_balancer():
    """Should return None when load_balancer key is missing."""
    status = {}
    assert service_external_ip(status) is None


def test_external_ip_dict_ingress_without_ip():
    """Should return None when ingress entry has no ip key."""
    status = {"load_balancer": {"ingress": [{"hostname": "example.com"}]}}
    assert service_external_ip(status) is None


def test_external_ip_object_with_ip():
    """Should extract IP from an object-style status."""
    ingress_entry = SimpleNamespace(ip="5.6.7.8")
    load_balancer = SimpleNamespace(ingress=[ingress_entry])
    status = SimpleNamespace(load_balancer=load_balancer)
    assert service_external_ip(status) == "5.6.7.8"


def test_external_ip_object_no_load_balancer():
    """Should return None when load_balancer attr is None."""
    status = SimpleNamespace(load_balancer=None)
    assert service_external_ip(status) is None


def test_external_ip_object_empty_ingress():
    """Should return None when ingress attr is empty list."""
    load_balancer = SimpleNamespace(ingress=[])
    status = SimpleNamespace(load_balancer=load_balancer)
    assert service_external_ip(status) is None


def test_external_ip_object_no_ingress():
    """Should return None when ingress attr is None."""
    load_balancer = SimpleNamespace(ingress=None)
    status = SimpleNamespace(load_balancer=load_balancer)
    assert service_external_ip(status) is None
