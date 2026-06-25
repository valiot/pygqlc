"""A stale/closed connection must be retried once on a fresh connection.

httpx reuses pooled keep-alive connections; when the server has already closed
one, the next request on it fails immediately with a transient transport error
(commonly `ReadError`/`RemoteProtocolError`, often with an empty message). A
single retry on a brand-new connection succeeds. `async_execute` must do that
retry instead of surfacing the error to the caller.
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
async def test_async_execute_retries_once_on_stale_connection(gql_env, monkeypatch):
    payload = {"data": {"createBulkThings": {"successful": True}}}
    client = AsyncMock()
    # First post hits a stale socket (ReadError); the retry on a fresh client succeeds.
    client.post = AsyncMock(side_effect=[httpx.ReadError(""), _fake_response(payload)])

    monkeypatch.setattr(gql_env, "_get_async_client", AsyncMock(return_value=client))
    dropped = AsyncMock()
    monkeypatch.setattr(gql_env, "_drop_async_client", dropped)

    result = await gql_env.async_execute("query { things { id } }")

    assert result == payload
    assert client.post.call_count == 2  # original + one retry
    dropped.assert_awaited_once()  # stale client was dropped before retrying


@pytest.mark.asyncio
async def test_async_execute_does_not_retry_read_timeout(gql_env, monkeypatch):
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ReadTimeout(""))
    monkeypatch.setattr(gql_env, "_get_async_client", AsyncMock(return_value=client))
    monkeypatch.setattr(gql_env, "_drop_async_client", AsyncMock())

    with pytest.raises(httpx.ReadTimeout):
        await gql_env.async_execute("query { things { id } }")

    assert client.post.call_count == 1  # not retried
