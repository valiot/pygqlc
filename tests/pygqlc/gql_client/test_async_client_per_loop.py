"""Regression tests: the async client must be per-event-loop, never shared.

httpx.AsyncClient's connection-pool primitives (asyncio Events/Locks inside
httpcore) bind to the event loop that first awaits them. 3.8.6 cached ONE
client per GraphQLClient instance, so a consumer running coroutines on more
than one loop — e.g. a Temporal worker's main loop plus a pygqlc subscription
thread calling ``asyncio.run(...)`` per callback (valuechainos-queues'
``trigger_by_subscription``) — failed with::

    RuntimeError: <asyncio.locks.Event object at 0x...> is bound to a different event loop

observed live as ``Error processing workflow QUEUE_REPLENISHMENT_FOR_CSV_REPORT``.

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
    gql.addEnvironment("per-loop-test", url="http://ex", default=True)
    yield gql
    gql._async_clients.clear()
    Singleton._instances.pop(GraphQLClient, None)


def test_each_loop_gets_its_own_client(client):
    """Two sequential asyncio.run loops must NOT share an httpx.AsyncClient."""
    seen = []

    async def grab():
        seen.append(await client._get_async_client())

    with patch("pygqlc.GraphQLClient.httpx.AsyncClient", side_effect=lambda **_: AsyncMock(is_closed=False)):
        asyncio.run(grab())
        asyncio.run(grab())

    assert len(seen) == 2
    assert seen[0] is not seen[1], "client leaked across event loops"


def test_same_loop_reuses_its_client(client):
    """Within one loop the client is still cached — no per-call churn (the 3.8.6 goal)."""
    seen = []

    async def grab_twice():
        seen.append(await client._get_async_client())
        seen.append(await client._get_async_client())

    with patch(
        "pygqlc.GraphQLClient.httpx.AsyncClient", side_effect=lambda **_: AsyncMock(is_closed=False)
    ) as ctor:
        asyncio.run(grab_twice())

    assert seen[0] is seen[1]
    assert ctor.call_count == 1


def test_async_execute_across_loops_posts_on_each_loops_client(client):
    """The field failure, pinned end-to-end: async_execute from two different
    loops must post on two different clients — never the first loop's."""
    response = MagicMock(status_code=200, content=b'{"data": {"ok": true}}')
    created = []

    def make_client(**_):
        mock = AsyncMock(is_closed=False)
        mock.post.return_value = response
        created.append(mock)
        return mock

    with patch("pygqlc.GraphQLClient.httpx.AsyncClient", side_effect=make_client) as ctor:
        asyncio.run(client.async_execute("query { ok }"))
        asyncio.run(client.async_execute("query { ok }"))

    assert ctor.call_count == 2, "second loop must build its own client"
    created[0].post.assert_awaited_once()
    created[1].post.assert_awaited_once()
