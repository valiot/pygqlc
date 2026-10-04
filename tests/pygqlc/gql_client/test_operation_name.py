"""`operation_name` selects one operation out of a multi-operation document.

A GraphQL request whose document defines several named operations must say
which one to run through the `operationName` field of the POST body. valiot-app
transactions depend on it: the document holds one named operation per step plus
a `RunTransaction` operation, and the server needs `operationName:
"RunTransaction"` to find the entry point.

These tests use a REAL local HTTP server (no mocks) that records the request
body it received and answers with a transaction-shaped payload.
"""

import http.server
import json
import threading

import pytest

from pygqlc import GraphQLClient

TRANSACTION = """
mutation StepOne { updateThing(id: 1, thing: {name: "a"}) { successful messages { message } } }
mutation StepTwo { updateThing(id: 2, thing: {name: "b"}) { successful messages { message } } }
mutation RunTransaction {
  executeTransaction(operations: ["StepOne", "StepTwo"]) {
    successful
    failedStep
    messages { field message }
  }
}
"""

RESPONSE = {
    "data": {
        "executeTransaction": {"successful": True, "failedStep": None, "messages": None}
    }
}


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Stores each POST body and answers with a successful transaction."""

    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        self.bodies.append(json.loads(self.rfile.read(length)))
        payload = json.dumps(RESPONSE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):  # silence the server access log
        pass


@pytest.fixture
def recorded_bodies():
    bodies = []
    _RecordingHandler.bodies = bodies
    server = http.server.HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    gql = GraphQLClient()
    gql.addEnvironment(
        "recording",
        url=f"http://{host}:{port}/api",
        wss="ws://127.0.0.1:1/socket/websocket",
        headers={"Authorization": "Bearer test"},
        post_timeout=5,
        default=True,
    )
    try:
        yield gql, bodies
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_mutate_sends_the_operation_name(recorded_bodies):
    gql, bodies = recorded_bodies

    data, errors = gql.mutate(TRANSACTION, operation_name="RunTransaction")

    assert errors == []
    assert data == {"successful": True, "failedStep": None, "messages": None}
    assert bodies[0]["operationName"] == "RunTransaction"


@pytest.mark.asyncio
async def test_async_mutate_sends_the_operation_name(recorded_bodies):
    gql, bodies = recorded_bodies

    data, errors = await gql.async_mutate(TRANSACTION, operation_name="RunTransaction")

    assert errors == []
    assert data["successful"] is True
    assert bodies[0]["operationName"] == "RunTransaction"


def test_a_request_without_an_operation_name_keeps_the_old_body(recorded_bodies):
    gql, bodies = recorded_bodies

    gql.mutate("mutation { deleteThing(id: 1) { successful messages { message } } }")

    assert set(bodies[0]) == {"query", "variables"}
