"""Regression tests: stale httpx.AsyncClient instances must be aclose()d, not
leaked to GC. Orphaned transports' _SelectorTransport.__del__ finalizers run
during cyclic-GC sweeps on arbitrary threads, which contributed to false
TMPRL1101 deadlocks in Temporal workers (see valiot/python-tooling#151).

Hermetic: no real sockets, no sleeps."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pygqlc import GraphQLClient
from pygqlc.helper_modules.Singleton import Singleton


@pytest.fixture
def client():
    """A fresh GraphQLClient (bypassing the process-wide singleton cache)."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("lifecycle-test", url="http://ex", default=True)
    yield gql
    gql._async_client = None  # never let teardown touch a mock
    Singleton._instances.pop(GraphQLClient, None)


@pytest.mark.asyncio
async def test_get_async_client_reuses_live_client(client):
    """A live client is reused on every call — never closed and recreated.

    Regression for the broken get_timeout() probe that closed + rebuilt the
    shared client on every call, churning connections and aborting concurrent
    requests with "client has been closed"."""
    live = AsyncMock()
    live.is_closed = False
    client._async_client = live

    with patch("pygqlc.GraphQLClient.httpx.AsyncClient") as new_client:
        first = await client._get_async_client()
        second = await client._get_async_client()

    assert first is live and second is live  # same client, reused
    new_client.assert_not_called()  # no new client created
    live.aclose.assert_not_awaited()  # live client never closed


@pytest.mark.asyncio
async def test_get_async_client_replaces_closed_client(client):
    """A client that has been closed is replaced with a fresh one."""
    closed = AsyncMock()
    closed.is_closed = True
    client._async_client = closed

    fresh = AsyncMock()
    with patch("pygqlc.GraphQLClient.httpx.AsyncClient", return_value=fresh):
        result = await client._get_async_client()

    assert result is fresh


@pytest.mark.asyncio
async def test_async_execute_retry_closes_stale_client(client):
    """The 'Event loop is closed' retry path in async_execute must aclose() the
    stale client before retrying with a new one."""
    stale = AsyncMock()
    stale.is_closed = False  # live, so _get_async_client returns it (then .post fails)
    stale.post.side_effect = RuntimeError("Event loop is closed")
    client._async_client = stale

    response = MagicMock(status_code=200, content=b'{"data": {"ok": true}}')
    fresh = AsyncMock()
    fresh.post.return_value = response

    with patch("pygqlc.GraphQLClient.httpx.AsyncClient", return_value=fresh):
        result = await client.async_execute("query { ok }")

    stale.aclose.assert_awaited_once()
    fresh.post.assert_awaited_once()
    assert result == {"data": {"ok": True}}


@pytest.mark.asyncio
async def test_close_schedules_aclose_on_running_loop(client):
    """_close() (sync, called by __del__) must schedule aclose() on the running
    loop instead of dropping the client to GC."""
    stale = AsyncMock()
    client._async_client = stale

    client._close()
    assert client._async_client is None

    # Let the call_soon_threadsafe callback and the task it creates run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    stale.aclose.assert_awaited_once()


def test_close_without_running_loop_falls_back_to_gc(client):
    """_close() outside any event loop must not raise — GC fallback as before."""
    stale = AsyncMock()
    client._async_client = stale

    client._close()

    assert client._async_client is None
    stale.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_drop_async_client_swallows_aclose_errors(client):
    """aclose() failing (original loop gone) must not propagate; the client is
    still dropped."""
    stale = AsyncMock()
    stale.aclose.side_effect = RuntimeError("Event loop is closed")
    client._async_client = stale

    await client._drop_async_client()

    stale.aclose.assert_awaited_once()
    assert client._async_client is None


@pytest.mark.asyncio
async def test_async_cleanup_closes_client(client):
    """async_cleanup must actually aclose() a live client (previously the broken
    get_timeout probe sent every client down the 'let GC handle it' branch)."""
    stale = AsyncMock()
    client._async_client = stale

    await client.async_cleanup()

    stale.aclose.assert_awaited_once()
    assert client._async_client is None
