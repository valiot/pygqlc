"""A request is sent again only when it provably never reached the server.

A mutation such as a bulk create has no unique key, so sending it twice stores
it twice. `execute` and `async_execute` therefore resend only when the request
was not written in full: a failure to connect (refused, connect timeout, pool
timeout), a pooled connection the server had already closed, or a closed
client or event loop. Once the whole request is on the wire, any failure (the
server drops or resets the connection, or answers too late) is raised to the
caller.

The connection tests use REAL local servers (HTTP/1.1, and HTTP/2 built on the
`h2` library) and a real `GraphQLClient`; the servers count the POSTs they
received and the connections they accepted.
"""

import asyncio
import http.server
import socket
import struct
import threading
import time
from unittest.mock import AsyncMock

import h2.config
import h2.connection
import h2.events
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
IDLE_CLOSE = 0.1  # how long a server keeps an idle connection in the *idle* modes
CLOSE_WAIT = 10  # upper bound for the server to report that it closed the connection


def _reset(sock):
    """Close with SO_LINGER 0, so the peer gets an RST instead of a FIN."""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()


class _CommittingHandler(http.server.BaseHTTPRequestHandler):
    """Reads and records ("commits") each POST, then answers as `mode` says:
    `ok` replies and keeps the connection alive, `idle_close` replies and
    closes the connection once it has been idle for IDLE_CLOSE, `drop` closes
    the connection, `reset` resets it, `stall` holds the reply until the test
    ends."""

    protocol_version = (
        "HTTP/1.1"  # keep-alive; the default HTTP/1.0 closes every connection
    )

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
            if self.server.mode == "idle_close":
                self.wfile.flush()
                time.sleep(IDLE_CLOSE)
                self.close_connection = True
        elif self.server.mode == "drop":
            self.close_connection = True
        elif self.server.mode == "reset":
            _reset(self.connection)
            self.close_connection = True
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
        self.connections = 0
        self.release = threading.Event()
        self.closed = threading.Event()
        self.thread = None

    def shutdown_request(self, request):
        super().shutdown_request(request)
        self.closed.set()

    def get_request(self):
        request = super().get_request()
        self.connections += 1
        return request

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


class _H2Server:
    """HTTP/2 with prior knowledge, which runs the same httpcore HTTP/2 code
    as `http2=True` against https. Each request is recorded and answered; then
    `mode` says what happens to the connection: `ok` keeps it,
    `fin_after_idle` / `rst_after_idle` close or reset it once it has been
    idle for IDLE_CLOSE with no GOAWAY (a crash, a killed pod, an LB reset),
    `commit_then_drop` records the second request and closes without
    answering."""

    def __init__(self, mode):
        self.mode = mode
        self.posts = []
        self.connections = 0
        self.closed = threading.Event()
        self.sock = socket.create_server(("127.0.0.1", 0))
        threading.Thread(target=self._accept, daemon=True).start()

    @property
    def url(self):
        host, port = self.sock.getsockname()
        return f"http://{host}:{port}/api"

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        h2_conn = h2.connection.H2Connection(
            h2.config.H2Configuration(client_side=False)
        )
        h2_conn.initiate_connection()
        conn.sendall(h2_conn.data_to_send())
        served = 0
        while True:
            idle_close = served and self.mode.endswith("_after_idle")
            conn.settimeout(IDLE_CLOSE if idle_close else None)
            try:
                data = conn.recv(65536)
            except TimeoutError:
                _reset(conn) if self.mode == "rst_after_idle" else conn.close()
                return self.closed.set()
            except OSError:
                return conn.close()
            if not data:
                return conn.close()
            for event in h2_conn.receive_data(data):
                if not isinstance(event, h2.events.StreamEnded):
                    continue
                served += 1
                self.posts.append(event.stream_id)
                if served == 2 and self.mode == "commit_then_drop":
                    return conn.close()
                self._answer(h2_conn, event.stream_id)
            conn.sendall(h2_conn.data_to_send())

    @staticmethod
    def _answer(h2_conn, stream_id):
        body = orjson.dumps(ANSWER)
        h2_conn.send_headers(
            stream_id,
            [
                (":status", "200"),
                ("content-type", "application/json"),
                ("content-length", str(len(body))),
            ],
        )
        h2_conn.send_data(stream_id, body, end_stream=True)

    def stop(self):
        self.sock.close()


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
def make_h2_server():
    servers = []

    def make(mode):
        server = _H2Server(mode)
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


def test_execute_reuses_a_kept_alive_connection(make_server, connect):
    server = make_server("ok")
    server.start()
    gql = connect(server)

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert (len(server.posts), server.connections) == (2, 1)


def test_execute_does_not_reuse_a_connection_the_server_closed_while_idle(
    make_server, connect
):
    # httpcore checks an HTTP/1.1 pooled connection before reusing it, so a
    # connection the server closed while idle is replaced, not written to.
    server = make_server("idle_close")
    server.start()
    gql = connect(server)

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    _wait_closed(server)
    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert (len(server.posts), server.connections) == (2, 2)


@pytest.mark.asyncio
async def test_async_execute_does_not_reuse_a_connection_the_server_closed_while_idle(
    make_server, connect
):
    server = make_server("idle_close")
    server.start()
    gql = connect(server)

    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    await asyncio.to_thread(_wait_closed, server)
    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    assert (len(server.posts), server.connections) == (2, 2)


def _wait_closed(server):
    """Block until the server has closed the idle connection, instead of
    sleeping a fixed time that a slow runner could overrun."""
    assert server.closed.wait(CLOSE_WAIT), "the server never closed the idle connection"


def _connect_h2(connect, server):
    gql = connect(server)
    gql.client_params["http1"] = False
    gql.async_client_params["http1"] = False
    return gql


# httpcore does not check an HTTP/2 pooled connection before reusing it: the
# request is written to the dead socket and fails before it was sent in full,
# so it is sent again on a new connection.
H2_STALE = ["fin_after_idle", "rst_after_idle"]


@pytest.mark.parametrize("mode", H2_STALE)
def test_execute_resends_on_an_http2_connection_the_server_closed_while_idle(
    make_h2_server, connect, mode
):
    server = make_h2_server(mode)
    gql = _connect_h2(connect, server)

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    _wait_closed(server)
    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    assert (len(server.posts), server.connections) == (2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", H2_STALE)
async def test_async_execute_resends_on_an_http2_connection_the_server_closed_while_idle(
    make_h2_server, connect, mode
):
    server = make_h2_server(mode)
    gql = _connect_h2(connect, server)

    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    await asyncio.to_thread(_wait_closed, server)
    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    assert (len(server.posts), server.connections) == (2, 2)


def test_execute_never_resends_an_http2_request_the_server_received(
    make_h2_server, connect
):
    server = make_h2_server("commit_then_drop")
    gql = _connect_h2(connect, server)

    assert gql.execute(MUTATION, VARIABLES) == ANSWER
    with pytest.raises(httpx.RemoteProtocolError):
        gql.execute(MUTATION, VARIABLES)
    assert (len(server.posts), server.connections) == (2, 1)


@pytest.mark.asyncio
async def test_async_execute_never_resends_an_http2_request_the_server_received(
    make_h2_server, connect
):
    server = make_h2_server("commit_then_drop")
    gql = _connect_h2(connect, server)

    assert await gql.async_execute(MUTATION, VARIABLES) == ANSWER
    with pytest.raises(httpx.RemoteProtocolError):
        await gql.async_execute(MUTATION, VARIABLES)
    assert (len(server.posts), server.connections) == (2, 1)


@pytest.mark.parametrize(
    "error,request_sent,expected",
    [
        (httpx.ConnectError(""), False, True),
        (httpx.ConnectTimeout(""), False, True),
        (httpx.PoolTimeout(""), False, True),
        (httpx.WriteError(""), False, True),
        (httpx.WriteTimeout(""), False, True),
        (RuntimeError("Event loop is closed"), False, True),
        (
            RuntimeError("Cannot send a request, as the client has been closed."),
            False,
            True,
        ),
        (httpx.WriteError(""), True, False),
        (httpx.ReadError(""), True, False),
        (httpx.RemoteProtocolError(""), True, False),
        (httpx.ReadTimeout(""), True, False),
        (ValueError("nope"), False, False),
    ],
)
def test_should_retry_on_fresh_connection(error, request_sent, expected):
    assert (
        GraphQLClient._should_retry_on_fresh_connection(error, request_sent) is expected
    )


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
