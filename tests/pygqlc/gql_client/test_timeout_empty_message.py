"""Transport exceptions must not collapse into a blank `[{"message": ""}]`.

httpx timeout and connection-reset exceptions carry an empty message, so
`str(error)` is "". When `execute`/`async_execute` raise one, the high-level
`query`/`mutate` helpers must still report a non-empty, diagnosable error that
preserves the exception type — not a meaningless `[{"message": ""}]` that hides
what actually failed.

These tests use a REAL local HTTP server (no mocks) that stalls past the
client's `post_timeout`, a real `GraphQLClient`, and a real mutation, so the
timeout and its empty message are produced by httpx itself.
"""

import http.server
import threading

import httpx
import pytest

from pygqlc import GraphQLClient
from pygqlc.GraphQLClient import exception_errors

MUTATION = """mutation($data:[CreateBulkThingParams]!){
  createBulkThings(things:$data){
    successful
    messages { message code field }
    result{things{id}}
  }
}
"""

VARIABLES = {"data": [{"name": "a"}, {"name": "b"}]}


def _mentions_timeout(message):
    lowered = message.lower()
    # async httpx -> repr "ReadTimeout('')"; sync httpx -> "timed out".
    return "timeout" in lowered or "timed out" in lowered


class _StallingHandler(http.server.BaseHTTPRequestHandler):
    """Accepts the POST, then sleeps long enough to trip the client read timeout."""

    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        # Sleep well past the client's post_timeout so httpx raises ReadTimeout.
        self._stall.wait(timeout=5)
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data": null}')
        except (BrokenPipeError, ConnectionResetError):
            # Client already timed out and closed the socket — expected.
            pass

    def log_message(self, *_args):  # silence the server access log
        pass


@pytest.fixture
def stalling_server():
    stall = threading.Event()
    _StallingHandler._stall = stall
    server = http.server.HTTPServer(("127.0.0.1", 0), _StallingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/api"
    finally:
        stall.set()  # release any in-flight handler
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def gql_to(stalling_server):
    gql = GraphQLClient()
    gql.addEnvironment(
        "stall",
        url=stalling_server,
        wss="ws://127.0.0.1:1/socket/websocket",
        headers={"Authorization": "Bearer test"},
        post_timeout=1,  # 1s; the server stalls ~5s
        default=True,
    )
    return gql


def test_exception_errors_preserves_type_when_message_is_blank():
    # httpx timeouts stringify to "" — the payload must not be blank.
    assert str(httpx.ReadTimeout("")) == ""
    [error] = exception_errors(httpx.ReadTimeout(""))
    assert error["message"].strip() != ""
    assert "ReadTimeout" in error["message"]


def test_exception_errors_keeps_a_real_message_verbatim():
    [error] = exception_errors(ValueError("boom"))
    assert error == {"message": "boom"}


@pytest.mark.asyncio
async def test_async_mutate_timeout_surfaces_diagnosable_error(gql_to):
    data, errors = await gql_to.async_mutate(MUTATION, variables=VARIABLES)

    assert data is None
    assert len(errors) == 1
    message = errors[0].get("message") or ""
    assert message.strip() != "", (
        "A timed-out request must not be reported as a blank message; "
        "the exception type must survive so the failure is diagnosable."
    )
    assert _mentions_timeout(message)


def test_mutate_timeout_surfaces_diagnosable_error(gql_to):
    data, errors = gql_to.mutate(MUTATION, variables=VARIABLES)

    assert data is None
    assert len(errors) == 1
    message = errors[0].get("message") or ""
    assert message.strip() != ""
    assert _mentions_timeout(message)
