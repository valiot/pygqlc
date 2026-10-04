"""A request is sent again only when it provably never reached the server.

A mutation such as a bulk create has no unique key, so sending it twice stores
it twice. `execute` and `async_execute` therefore resend only after a failure
to connect (refused, connect timeout, pool timeout) or on a closed client or
event loop. Once the request is on the wire, any failure (the server drops or
resets the connection, or answers too late) is raised to the caller.

The connection tests use a REAL local HTTP server and a real `GraphQLClient`;
the server counts the POSTs it received.
"""

import http.server
import socket
import struct
import threading
from unittest.mock import AsyncMock

import httpx
import orjson
import pytest

from pygqlc import GraphQLClient

MUTATION = """mutation($data:[CreateBulkThingParams]!){
  createBulkThings(things:$data){ successful }
}
"""
VARIABLES = {"data": [{"name": "a"}]}
ANSWER = {"data": {"createBulkThings": {"successful": True}}}


class _CommittingHandler(http.server.BaseHTTPRequestHandler):
    """Reads and records ("commits") each POST, then answers as `mode` says:
    `ok` replies, `idle_close` replies and then closes the kept-alive
    connection, `drop` closes the connection, `reset` resets it, `stall` holds
    the reply until the test ends."""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.posts.append(self.path)
        if self.server.mode in ("ok", "idle_close"):
            body = orjson.dumps(ANSWER)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = self.server.mode == "idle_close"
        elif self.server.mode == "drop":
            self.close_connection = True
        elif self.server.mode == "reset":
            linger_zero = struct.pack("ii", 1, 0)
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger_zero)
            self.connection.close()
        elif self.server.mode == "stall":
            self.server.release.wait(timeout=10)
            self.close_connection = True

    def log_message(self, *_args):
        pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, mode):
        # Bound but not listening: until `start()`, connections are refused.
        super().__init__(("127.0.0.1", 0), _CommittingHandler, bind_and_activate=False)
        self.server_bind()
        self.mode = mode
        self.posts = []
        self.release = threading.Event()
        self.thread = None

    @property
    def url(self):
        host, port = self.server_address
        return f"http://{host}:{port}/api"

    def start(self):
        self.server_activate()
        self.thread = threading.Thread(
            target=self.serve_forever, args=(0.05,), daemon=True
        )
        self.thread.start()

    def stop(self):
        self.release.set()
        if self.thread:
            self.shutdown()
            self.thread.join(timeout=5)
        self.server_close()


@pytest.fixture
def make_server():
    servers = []

    def make(mode):
        server = _Server(mode)
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.stop()


@pytest.fixture
def connect():
    """`GraphQLClient` is a process-wide singleton. Each test gets fresh HTTP
    clients and an environment pointed at its server; the previous
    environment and client params are put back afterwards."""
    gql = GraphQLClient()
    saved_params = dict(gql.client_params), dict(gql.async_client_params)
    gql._close()
    gql.addEnvironment(
        "resend-test",
        wss="ws://127.0.0.1:1/socket/websocket",
        headers={"Authorization": "Bearer test"},
        post_timeout=0.5,
    )

    def point_at(server):
        gql.addEnvironment("resend-test", url=server.url)
        return gql

    with gql.enterEnvironment("resend-test"):
        yield point_at
    gql._close()
    gql.client_params, gql.async_client_params = saved_params


def _listen_on_second_attempt(server):
    """Request hook: the first attempt finds the port refusing connections;
    the server starts listening just before the second attempt connects."""
    attempts = []

    def on_request(_request):
        attempts.append(1)
        if len(attempts) == 2:
            server.start()

    return attempts, on_request


def test_execute_resends_after_a_refused_connection(make_server, connect):
    server = make_server("ok")
    attempts, on_request = _listen_on_second_attempt(server)
    gql = connect(server)
    gql.client_params["event_hooks"] = {"request": [on_request]}

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert len(attempts) == 2
    assert len(server.posts) == 1


@pytest.mark.asyncio
async def test_async_execute_resends_after_a_refused_connection(make_server, connect):
    server = make_server("ok")
    attempts, on_request = _listen_on_second_attempt(server)

    async def on_request_async(request):
        on_request(request)

    gql = connect(server)
    gql.async_client_params["event_hooks"] = {"request": [on_request_async]}

    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    assert len(attempts) == 2
    assert len(server.posts) == 1


FAILURES_AFTER_COMMIT = [
    ("drop", httpx.RemoteProtocolError),
    ("reset", httpx.ReadError),
    ("stall", httpx.ReadTimeout),
]


@pytest.mark.parametrize("mode,error", FAILURES_AFTER_COMMIT)
def test_execute_never_resends_a_request_the_server_received(
    make_server, connect, mode, error
):
    server = make_server(mode)
    server.start()
    gql = connect(server)

    with pytest.raises(error):
        gql.execute(MUTATION, VARIABLES)
    assert len(server.posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,error", FAILURES_AFTER_COMMIT)
async def test_async_execute_never_resends_a_request_the_server_received(
    make_server, connect, mode, error
):
    server = make_server(mode)
    server.start()
    gql = connect(server)

    with pytest.raises(error):
        await gql.async_execute(MUTATION, VARIABLES)
    assert len(server.posts) == 1


def test_mutate_reports_the_lost_answer_as_an_error(make_server, connect):
    server = make_server("drop")
    server.start()
    gql = connect(server)

    data, errors = gql.mutate(MUTATION, VARIABLES)

    assert data is None
    assert errors and errors[0]["message"].strip()
    assert len(server.posts) == 1


def test_execute_does_not_reuse_a_connection_the_server_closed_while_idle(
    make_server, connect
):
    # 3.8.4 resent after ReadError to survive stale keep-alive sockets. httpcore
    # already discards a pooled connection the server closed before reusing it,
    # so dropping that resend does not turn stale sockets into errors.
    server = make_server("idle_close")
    server.start()
    gql = connect(server)

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert len(server.posts) == 2


@pytest.mark.asyncio
async def test_async_execute_does_not_reuse_a_connection_the_server_closed_while_idle(
    make_server, connect
):
    server = make_server("idle_close")
    server.start()
    gql = connect(server)

    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    assert len(server.posts) == 2


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ConnectError(""), True),
        (httpx.ConnectTimeout(""), True),
        (httpx.PoolTimeout(""), True),
        (RuntimeError("Event loop is closed"), True),
        (RuntimeError("Cannot send a request, as the client has been closed."), True),
        (httpx.ReadError(""), False),
        (httpx.WriteError(""), False),
        (httpx.RemoteProtocolError(""), False),
        (httpx.ReadTimeout(""), False),
        (httpx.WriteTimeout(""), False),
        (ValueError("nope"), False),
    ],
)
def test_should_retry_on_fresh_connection(error, expected):
    assert GraphQLClient._should_retry_on_fresh_connection(error) is expected


@pytest.mark.asyncio
async def test_async_execute_rebuilds_client_on_closed_event_loop(
    make_server, connect, monkeypatch
):
    # A dead event loop cannot be reproduced against the per-loop client cache,
    # so this one case stubs the client.
    gql = connect(make_server("ok"))
    dead = AsyncMock()
    dead.post = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
    fresh = AsyncMock()
    fresh.post = AsyncMock(
        return_value=httpx.Response(status_code=200, content=orjson.dumps(ANSWER))
    )
    monkeypatch.setattr(gql, "_get_async_client", AsyncMock(side_effect=[dead, fresh]))
    dropped = AsyncMock()
    monkeypatch.setattr(gql, "_drop_async_client", dropped)

    assert await gql.async_execute("query { things { id } }") == ANSWER
    dead.post.assert_awaited_once()
    fresh.post.assert_awaited_once()
    dropped.assert_awaited_once()
