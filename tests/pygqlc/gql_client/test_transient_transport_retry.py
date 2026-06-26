"""A stale/closed pooled connection must be retried once on a fresh one.

When the server has closed a pooled keep-alive connection, the next request
fails with a transient transport error (e.g. `ReadError('')`). `async_execute`
should retry once on a new connection instead of surfacing it.
"""

from unittest.mock import AsyncMock

import httpx
import orjson
import pytest

from pygqlc import GraphQLClient


def _fake_response(payload):
    resp = httpx.Response(status_code=200, content=orjson.dumps(payload))
    return resp


@pytest.fixture
def gql_env():
    gql = GraphQLClient()
    gql.addEnvironment(
        "retry-test",
        url="http://127.0.0.1:1/api",
        wss="ws://127.0.0.1:1/socket/websocket",
        headers={"Authorization": "Bearer test"},
        post_timeout=5,
        default=True,
    )
    return gql


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ReadError(""), True),
        (httpx.RemoteProtocolError(""), True),
        (httpx.ConnectTimeout(""), True),
        (httpx.PoolTimeout(""), True),
        (httpx.ConnectError(""), True),
        (RuntimeError("Event loop is closed"), True),
        (httpx.ReadTimeout(""), False),  # genuine slow request — don't auto-retry
        (ValueError("nope"), False),
    ],
)
def test_should_retry_on_fresh_connection(error, expected):
    assert GraphQLClient._should_retry_on_fresh_connection(error) is expected


@pytest.mark.asyncio
async def test_async_execute_retries_stale_connection_without_dropping_pool(
    gql_env, monkeypatch
):
    payload = {"data": {"createBulkThings": {"successful": True}}}
    # Same shared client: first post hits a stale socket, retry succeeds.
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[httpx.ReadError(""), _fake_response(payload)])

    monkeypatch.setattr(gql_env, "_get_async_client", AsyncMock(return_value=client))
    dropped = AsyncMock()
    monkeypatch.setattr(gql_env, "_drop_async_client", dropped)

    result = await gql_env.async_execute("query { things { id } }")

    assert result == payload
    assert client.post.call_count == 2  # retried on the same client
    # Crucially: the shared pool is NOT torn down for a stale connection — doing
    # so under concurrency would abort other in-flight requests (churn storm).
    dropped.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_execute_rebuilds_client_on_closed_event_loop(gql_env, monkeypatch):
    payload = {"data": {"createBulkThings": {"successful": True}}}
    # A closed event loop DOES invalidate the whole client, so it is dropped and
    # rebuilt before retrying.
    dead = AsyncMock()
    dead.post = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
    fresh = AsyncMock()
    fresh.post = AsyncMock(return_value=_fake_response(payload))

    monkeypatch.setattr(
        gql_env, "_get_async_client", AsyncMock(side_effect=[dead, fresh])
    )
    dropped = AsyncMock()
    monkeypatch.setattr(gql_env, "_drop_async_client", dropped)

    result = await gql_env.async_execute("query { things { id } }")

    assert result == payload
    dead.post.assert_awaited_once()
    fresh.post.assert_awaited_once()
    dropped.assert_awaited_once()  # whole client rebuilt for a dead event loop


@pytest.mark.asyncio
async def test_async_execute_does_not_retry_read_timeout(gql_env, monkeypatch):
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ReadTimeout(""))
    monkeypatch.setattr(gql_env, "_get_async_client", AsyncMock(return_value=client))
    monkeypatch.setattr(gql_env, "_drop_async_client", AsyncMock())

    with pytest.raises(httpx.ReadTimeout):
        await gql_env.async_execute("query { things { id } }")

    assert client.post.call_count == 1  # not retried
