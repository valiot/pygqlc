"""Operation hooks: a consumer can observe every operation the client runs.

A hook is a function registered with `pygqlc.hooks.add_operation_hook`. It is
called once per operation (after `execute`/`async_execute` finish, retries
included) and once per subscription message, with an `OperationEvent`: what ran,
when, how long it took, and what came back or failed. Hooks only observe: the
operation's result and errors reach the caller exactly as without them.

Requests go to a REAL local HTTP server (no mocks); subscription messages are fed
to the subscription loop the way the websocket router does.
"""

import http.server
import json
import threading

import pytest

from pygqlc import GraphQLClient, hooks
from pygqlc.helper_modules.Singleton import Singleton

PLANS = "query Plans { plans { id } }"
UPDATE = "mutation { updatePlan(id: 1) { successful messages { message } } }"


class _Server(http.server.BaseHTTPRequestHandler):
    """Answers each POST with `status` and `payload` (class attributes)."""

    status = 200
    payload: dict = {}

    def do_POST(self):  # noqa: N802 (http.server API)
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(self.payload).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def server():
    _Server.status = 200
    _Server.payload = {"data": {"plans": [{"id": "1"}, {"id": "2"}]}}
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Server)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    gql = GraphQLClient()
    host, port = httpd.server_address
    gql.addEnvironment(
        "hooks-test",
        url=f"http://{host}:{port}/api",
        wss="ws://127.0.0.1:1/socket/websocket",
        post_timeout=5,
    )
    try:
        with gql.enterEnvironment("hooks-test"):
            yield gql
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def events():
    received = []
    hooks.add_operation_hook(received.append)
    yield received
    hooks.remove_operation_hook(received.append)


def test_a_query_is_reported_with_its_name_timing_and_response(server, events):
    data, errors = server.query(PLANS)

    assert errors == []
    assert data == [{"id": "1"}, {"id": "2"}]
    [event] = events
    assert event.kind == "query"
    assert event.name == "Plans"
    assert event.environment == "hooks-test"
    assert event.document == PLANS
    assert event.started_at > 0
    assert event.duration > 0
    assert event.response == {"data": {"plans": [{"id": "1"}, {"id": "2"}]}}
    assert event.error is None


@pytest.mark.asyncio
async def test_an_async_mutation_is_reported_as_a_mutation(server, events):
    _Server.payload = {"data": {"updatePlan": {"successful": True, "messages": []}}}

    await server.async_mutate(UPDATE, operation_name=None)

    [event] = events
    assert event.kind == "mutation"
    assert event.name == "anonymous"
    assert event.response["data"]["updatePlan"]["successful"] is True


def test_an_operation_name_picks_the_operation_it_names(server, events):
    document = "query Plans { plans { id } }\nmutation Save { save { successful } }"
    _Server.payload = {"data": {"save": {"successful": True}}}

    server.mutate(document, operation_name="Save")

    [event] = events
    assert (event.kind, event.name) == ("mutation", "Save")


def test_a_failed_request_is_reported_with_its_error_and_still_returns_errors(
    server, events
):
    _Server.status = 500
    _Server.payload = {"errors": [{"message": "boom"}]}

    data, errors = server.mutate(UPDATE)

    assert data is None
    assert errors and "500" in errors[0]["message"]
    [event] = events
    assert event.response is None
    assert getattr(event.error, "status_code", None) == 500


def test_a_hook_that_raises_does_not_change_the_result(server, events):
    def broken(_event):
        raise RuntimeError("hook bug")

    hooks.add_operation_hook(broken)
    try:
        data, errors = server.query(PLANS)
    finally:
        hooks.remove_operation_hook(broken)

    assert errors == []
    assert data == [{"id": "1"}, {"id": "2"}]
    assert len(events) == 1


def test_a_removed_hook_is_not_called(server):
    received = []
    hooks.add_operation_hook(received.append)
    hooks.remove_operation_hook(received.append)

    server.query(PLANS)

    assert received == []


def test_a_subscription_message_is_reported(events):
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("hooks-sub", url="http://ex", wss="ws://ex", default=True)
    gql.poll_interval = 0
    document = "subscription PlanUpdated { planUpdated { id } }"
    gql.subs = {
        "1": {
            "running": False,
            "kill": False,
            "flatten": True,
            "query": document,
            "variables": {"id": 1},
            "queue": [
                {"id": "1", "type": "next", "payload": {"data": {"planUpdated": {"id": "7"}}}},
                {"id": "1", "type": "complete"},
            ],
        }
    }
    delivered = []
    try:
        gql._subscription_loop(delivered.append, "1", None)
    finally:
        gql.closing = True
        Singleton._instances.pop(GraphQLClient, None)

    assert delivered == [{"id": "7"}]
    [event] = events
    assert (event.kind, event.name) == ("subscription", "PlanUpdated")
    assert event.variables == {"id": 1}
    assert event.duration == 0
    assert event.response == {"data": {"planUpdated": {"id": "7"}}}
