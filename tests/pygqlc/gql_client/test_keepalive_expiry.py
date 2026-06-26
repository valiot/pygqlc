"""Idle keep-alive connections are retired quickly via httpx ``keepalive_expiry``
so a socket the server already closed is never reused — the stale keep-alive that
surfaces as ``ReadError('')``. Default 2s, tunable via ``PYGQLC_KEEPALIVE_EXPIRY``.
"""

import httpx
import pytest

from pygqlc import GraphQLClient
from pygqlc.GraphQLClient import DEFAULT_KEEPALIVE_EXPIRY
from pygqlc.helper_modules.Singleton import Singleton


@pytest.fixture
def fresh_client():
    """Build GraphQLClient instances whose ``__init__`` re-reads the env, without
    leaking state into the process-wide singleton other tests share."""
    saved = Singleton._instances.pop(GraphQLClient, None)

    def _build():
        Singleton._instances.pop(GraphQLClient, None)
        return GraphQLClient()

    yield _build

    Singleton._instances.pop(GraphQLClient, None)
    if saved is not None:
        Singleton._instances[GraphQLClient] = saved


def test_default_keepalive_expiry_on_both_clients(fresh_client, monkeypatch):
    monkeypatch.delenv("PYGQLC_KEEPALIVE_EXPIRY", raising=False)
    gql = fresh_client()
    for params in (gql.client_params, gql.async_client_params):
        limits = params["limits"]
        assert isinstance(limits, httpx.Limits)
        assert limits.keepalive_expiry == DEFAULT_KEEPALIVE_EXPIRY
        # httpx's standard pool caps must be preserved, not reset to None.
        assert limits.max_connections == 100
        assert limits.max_keepalive_connections == 20


def test_keepalive_expiry_env_override(fresh_client, monkeypatch):
    monkeypatch.setenv("PYGQLC_KEEPALIVE_EXPIRY", "0.5")
    gql = fresh_client()
    assert gql.client_params["limits"].keepalive_expiry == 0.5
    assert gql.async_client_params["limits"].keepalive_expiry == 0.5


def test_default_below_httpx_default():
    # The point of the mitigation: shorter than httpx's own default so a
    # server/LB with a shorter idle timeout can't close the socket first.
    # Compare against the live httpx default so this doesn't go stale on upgrades.
    assert DEFAULT_KEEPALIVE_EXPIRY < httpx.Limits().keepalive_expiry


def test_invalid_env_falls_back_to_default(fresh_client, monkeypatch):
    monkeypatch.setenv("PYGQLC_KEEPALIVE_EXPIRY", "not-a-number")
    gql = fresh_client()
    assert gql.client_params["limits"].keepalive_expiry == DEFAULT_KEEPALIVE_EXPIRY


def test_negative_env_falls_back_to_default(fresh_client, monkeypatch):
    monkeypatch.setenv("PYGQLC_KEEPALIVE_EXPIRY", "-5")
    gql = fresh_client()
    assert gql.client_params["limits"].keepalive_expiry == DEFAULT_KEEPALIVE_EXPIRY


def test_ipv4_only_threads_limits_into_transports(fresh_client, monkeypatch):
    """In ipv4_only mode a custom transport is installed; httpx ignores the
    Client-level limits there, so the limits must be passed into the transport."""
    gql = fresh_client()
    captured = {}

    def fake_http_transport(**kwargs):
        captured["sync"] = kwargs
        return object()

    def fake_async_transport(**kwargs):
        captured["async"] = kwargs
        return object()

    monkeypatch.setattr(httpx, "HTTPTransport", fake_http_transport)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", fake_async_transport)

    gql._update_client_params(ipv4_only=True)

    assert captured["sync"]["limits"] is gql._limits
    assert captured["async"]["limits"] is gql._limits
    assert captured["sync"]["local_address"] == "0.0.0.0"
    assert captured["async"]["local_address"] == "0.0.0.0"
