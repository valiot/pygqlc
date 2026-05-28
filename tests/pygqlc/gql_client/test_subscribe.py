from . import subscriptions as subs
from . import mutations as muts
import types
import time

import threading
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from pygqlc import GraphQLClient
from pygqlc.helper_modules.Singleton import Singleton
from pygqlc.logging import LogLevel, get_logger, set_logger


def on_author_updated(msg):
    if msg["successful"]:
        author = msg["result"]
        print(f"author {author['name']} was updated successfully")
    else:
        print(f"error creating author: {msg['messages']}")


def on_author_created(msg):
    if msg["successful"]:
        author = msg["result"]
        print(f"author {author['name']} was created successfully")
    else:
        print(f"error creating author: {msg['messages']}")


def test_subscribe_success(gql):
    sub_id = str(gql.sub_counter + 1)
    unsub_1 = gql.subscribe(subs.sub_author_created, callback=on_author_created)
    assert type(unsub_1) == types.FunctionType, (
        "subscribe should return an unsubscribe function"
    )
    assert len(gql.subs.items()) > 0, "There should be at least ONE subscription active"
    assert gql.subs.get(sub_id) is not None, (
        "The subscription did not start with the correct ID"
    )


def test_sub_routing_loop_message(gql):
    sub_id = str(gql.sub_counter + 1)
    _ = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
    runs = gql.subs[sub_id]["runs"]
    # * This should activate the subscription at least once:
    _ = gql.mutate(
        muts.update_any_author_active,
        {"name": "Elon", "lastname": "Musk", "active": True},
    )
    _ = gql.mutate(
        muts.update_any_author_active,
        {"name": "Elon", "lastname": "Musk", "active": False},
    )
    # ! We don't know how long will it take for the server to respond to the subscription:
    sub_triggered = False
    elapsed = 0
    timeout = 5.0  # * Max seconds to wait
    startTime = time.time()
    while not sub_triggered and elapsed < timeout:
        new_runs = gql.subs[sub_id]["runs"]
        sub_triggered = new_runs > runs
        time.sleep(0.01)  # * Give time to de server to react to the request
        elapsed = time.time() - startTime
    assert sub_triggered, "Subscription should be triggered at least once"


def test_sub_default_callback(gql):
    sub_id = str(gql.sub_counter + 1)
    # * This adds coverage into the default callback
    _ = gql.subscribe(subs.sub_author_updated)
    runs = gql.subs[sub_id]["runs"]
    # * This should activate the subscription at least once:
    _ = gql.mutate(
        muts.update_any_author_active,
        {"name": "Elon", "lastname": "Musk", "active": True},
    )
    _ = gql.mutate(
        muts.update_any_author_active,
        {"name": "Elon", "lastname": "Musk", "active": False},
    )
    # ! We don't know how long will it take for the server to respond to the subscription:
    sub_triggered = False
    elapsed = 0
    timeout = 5.0  # * Max seconds to wait
    startTime = time.time()
    while not sub_triggered and elapsed < timeout:
        new_runs = gql.subs[sub_id]["runs"]
        sub_triggered = new_runs > runs
        time.sleep(0.01)  # * Give time to de server to react to the request
        elapsed = time.time() - startTime
    assert new_runs > runs, (
        "Subscription should be triggered at least once with default callback"
    )


# from pygqlc import GraphQLClient
# from tests.pygqlc import subscriptions as subs
# from tests.pygqlc import mutations as muts
# gql = GraphQLClient()

# unsub_1 = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
# unsub_2 = gql.subscribe(subs.sub_author_created, callback=on_author_created)

# ! To trigger subscription:
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': True})
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': False})
# data, errors = gql.mutate(muts.create_author, {'name': 'Juanito', 'lastName': 'Saldi'})

# ! to exit:
# >> gql.close()
# >> exit()


@contextmanager
def _capture_logs():
    """Record (level, message) tuples emitted via pygqlc's log() during the block."""
    records = []
    previous = get_logger()
    set_logger(lambda level, message, extra=None: records.append((level, message)))
    try:
        yield records
    finally:
        set_logger(previous)


def _run_routing_loop(gql, timeout=5.0):
    """Run _sub_routing_loop in a daemon thread; fail (not hang) if it doesn't exit."""
    thread = threading.Thread(target=gql._sub_routing_loop, daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "routing loop did not terminate"


def _stop_loop_on(gql):
    """Return a _new_conn replacement that halts the loop after one reconnect attempt."""

    def _stop():
        gql.closing = True
        return False

    return _stop


@pytest.fixture
def routing_client():
    """A fresh GraphQLClient (bypassing the process-wide singleton cache) wired to a mock
    websocket connection, with the routing loop's sleeps disabled for determinism."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("routing-test", url="http://ex", wss="ws://ex", default=True)
    conn = MagicMock()
    conn.settimeout.return_value = None
    conn.close.return_value = None
    gql._conn = conn
    gql.subs = {}
    gql.poll_interval = 0
    yield gql
    gql.closing = True
    Singleton._instances.pop(GraphQLClient, None)


def test_sub_routing_loop_non_dict_message_triggers_reconnect(routing_client):
    """OPS-3485: a non-dict payload (orjson.loads(b'null') -> None) must not crash the
    router on `.get`; it should log a WARNING and halt to trigger reconnection."""
    gql = routing_client
    gql._conn.recv.return_value = b"null"

    with (
        patch.object(gql, "_new_conn", side_effect=_stop_loop_on(gql)) as new_conn,
        _capture_logs() as records,
    ):
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(
        level == LogLevel.WARNING and "invalid WSS message" in msg
        for level, msg in records
    )
    assert not any(level == LogLevel.ERROR for level, msg in records)


def test_sub_routing_loop_connection_reset_logged_as_warning(routing_client):
    """OPS-3485: ConnectionResetError from recv is transient — log at WARNING (not
    ERROR+traceback) and halt for reconnection."""
    gql = routing_client
    gql._conn.recv.side_effect = ConnectionResetError(104, "Connection reset by peer")

    with (
        patch.object(gql, "_new_conn", side_effect=_stop_loop_on(gql)) as new_conn,
        _capture_logs() as records,
    ):
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(
        level == LogLevel.WARNING and "reset or closed by peer" in msg
        for level, msg in records
    )
    assert not any(
        level == LogLevel.ERROR and "Some error trying to receive WSS" in msg
        for level, msg in records
    )


def test_sub_routing_loop_unexpected_error_logged_as_error(routing_client):
    """A non-transient error (not in TRANSIENT_WS_ERRORS) must still surface at ERROR
    level and halt for reconnection."""
    gql = routing_client
    gql._conn.recv.side_effect = ValueError("unexpected wire failure")

    with (
        patch.object(gql, "_new_conn", side_effect=_stop_loop_on(gql)) as new_conn,
        _capture_logs() as records,
    ):
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(
        level == LogLevel.ERROR and "Some error trying to receive WSS" in msg
        for level, msg in records
    )


def test_sub_routing_loop_valid_message_does_not_halt(routing_client):
    """Regression: a well-formed dict message routes normally without halting or
    triggering reconnection."""
    gql = routing_client

    def _recv_then_close():
        gql.closing = True
        return b'{"type":"pong"}'

    gql._conn.recv.side_effect = _recv_then_close

    with patch.object(gql, "_new_conn") as new_conn, _capture_logs() as records:
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is False
    new_conn.assert_not_called()
    assert not any(level == LogLevel.ERROR for level, msg in records)
    assert not any("invalid WSS message" in msg for level, msg in records)


@pytest.fixture
def pingpong_client():
    """A fresh GraphQLClient (bypassing singleton) wired to mock conn for _ping_pong tests.
    Sleeps and intervals tuned for fast deterministic runs."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("ping-test", url="http://ex", wss="ws://ex", default=True)
    conn = MagicMock()
    conn.settimeout.return_value = None
    conn.close.return_value = None
    conn.send.return_value = None
    gql._conn = conn
    gql.subs = {}
    gql.poll_interval = 0
    gql.pingIntervalTime = 15
    gql.pingTimer = time.time()
    gql.wss_conn_halted = False
    gql.closing = False
    yield gql
    gql.closing = True
    Singleton._instances.pop(GraphQLClient, None)


def _run_ping_pong_loop(gql, timeout=2.0):
    """Run _ping_pong in daemon thread (loops until .closing)."""
    thread = threading.Thread(target=gql._ping_pong, daemon=True)
    thread.start()
    thread.join(timeout)
    return thread


def test_ping_pong_connection_reset_logged_as_warning(pingpong_client):
    """OPS-3500: ConnectionResetError (and other TRANSIENT_WS_ERRORS) from send(PING)
    must log at WARNING (no traceback) like recv path, set halted=True, and trigger reconnect."""
    gql = pingpong_client
    gql.pingIntervalTime = 0

    call_count = {"n": 0}

    def _send_then_stop(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionResetError(104, "Connection reset by peer")
        else:
            gql.closing = True
            return None

    gql._conn.send.side_effect = _send_then_stop

    with _capture_logs() as records:
        _run_ping_pong_loop(gql)

    assert gql.wss_conn_halted is True
    assert any(
        level == LogLevel.WARNING and "reset or closed by peer" in msg
        for level, msg in records
    ), f"expected WARNING, got: {records}"
    assert not any(
        level == LogLevel.ERROR and "error trying to send ping" in msg
        for level, msg in records
    ), f"should not have ping ERROR log, got: {records}"


def test_ping_pong_unexpected_error_logged_as_error(pingpong_client):
    """Non-transient error from ping send must log at ERROR (preserving prior behavior for real bugs)."""
    gql = pingpong_client
    gql.pingIntervalTime = 0

    call_count = {"n": 0}

    def _send_then_stop(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("unexpected send failure during ping")
        else:
            gql.closing = True
            return None

    gql._conn.send.side_effect = _send_then_stop

    with _capture_logs() as records:
        _run_ping_pong_loop(gql)

    assert gql.wss_conn_halted is True
    assert any(
        level == LogLevel.ERROR
        and "error trying to send ping, WSS Pipe is broken" in msg
        for level, msg in records
    )


def test_ping_pong_normal_operation_does_not_halt(pingpong_client):
    """Regression: normal pings do not halt or log errors/warnings."""
    gql = pingpong_client
    gql.pingIntervalTime = 0
    call_count = {"n": 0}

    def _send_then_close(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            gql.closing = True
        return None

    gql._conn.send.side_effect = _send_then_close

    with _capture_logs() as records:
        _run_ping_pong_loop(gql)

    assert gql.wss_conn_halted is False
    assert not any(level == LogLevel.ERROR for level, msg in records)
    assert not any(
        level == LogLevel.WARNING and "reset or closed" in msg for level, msg in records
    )
