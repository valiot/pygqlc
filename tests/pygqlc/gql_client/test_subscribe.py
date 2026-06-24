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


def test_addenvironment_reregister_preserves_wss():
    """OPS-3496: re-registering an existing environment without `wss` (as a library
    configuring the shared Singleton client does) must NOT wipe the previously-set
    wss/url/headers/post_timeout. The clobber is what reset ws_url to None and crashed
    the live reconnect loop. Provided fields still override; omitted fields are kept."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment(
        "prod",
        url="http://api",
        wss="ws://live",
        headers={"Authorization": "Bearer host"},
        post_timeout=120,
        default=True,
    )
    # A second consumer re-registers the same env without wss (the OPS-3496 trigger):
    gql.addEnvironment(
        "prod", url="http://api", headers={"Authorization": "Bearer other"}
    )
    env = gql.environments["prod"]
    assert env["wss"] == "ws://live", "wss must survive re-registration"
    assert env["post_timeout"] == 120, "post_timeout must survive re-registration"
    assert env["headers"]["Authorization"] == "Bearer other", (
        "explicitly provided fields must still override"
    )
    Singleton._instances.pop(GraphQLClient, None)


def test_new_conn_returns_false_when_wss_missing():
    """OPS-3496: _new_conn must fail gracefully (log ERROR, return False) instead of
    raising TypeError inside websocket.create_connection when wss is None."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("no-wss", url="http://api", wss=None, default=True)
    with _capture_logs() as records:
        result = gql._new_conn()
    assert result is False
    assert any(level == LogLevel.ERROR for level, _ in records)
    Singleton._instances.pop(GraphQLClient, None)


def test_new_conn_returns_false_when_no_environment():
    """OPS-3496: _new_conn must not raise AttributeError when no environment is set;
    it returns False and logs an ERROR so the router thread survives."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    with _capture_logs() as records:
        result = gql._new_conn()
    assert result is False
    assert any(level == LogLevel.ERROR for level, _ in records)
    Singleton._instances.pop(GraphQLClient, None)


def test_new_conn_closes_previous_connection_on_reconnect():
    """A reconnect must cleanly close the previous socket before opening a new one,
    so the stitchex server receives a FIN and tears down the stale subscription.
    Previously _new_conn abandoned the old self._conn (half-open socket leak) and
    the server kept fanning subscription data into it until it OOMed."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("reconnect-test", url="http://ex", wss="ws://ex", default=True)
    old_conn = MagicMock()
    gql._conn = old_conn
    new_conn = MagicMock()

    with (
        patch(
            "pygqlc.GraphQLClient.websocket.create_connection",
            return_value=new_conn,
        ),
        patch.object(gql, "_conn_init"),
    ):
        result = gql._new_conn()

    assert result is True
    old_conn.close.assert_called_once()
    assert gql._conn is new_conn, "the new connection must replace the old one"
    Singleton._instances.pop(GraphQLClient, None)


def test_multiple_subscriptions_share_one_connection():
    """graphql-transport-ws multiplexes every subscription over a SINGLE socket,
    keyed by id. subscribe() opens the connection only when self._conn is unset
    (the `if not self._conn` guard), so the 2nd/3rd/... subscriptions reuse it and
    never call _new_conn. This guards the close-on-reconnect fix: _close_conn must
    never tear down a live connection that still has active subscriptions on it."""
    Singleton._instances.pop(GraphQLClient, None)
    gql = GraphQLClient()
    gql.addEnvironment("multisub-test", url="http://ex", wss="ws://ex", default=True)
    gql.subs = {}
    gql.poll_interval = 0
    created = []

    def make_conn(*_args, **_kwargs):
        conn = MagicMock(name=f"conn{len(created)}")
        created.append(conn)
        return conn

    with (
        patch(
            "pygqlc.GraphQLClient.websocket.create_connection", side_effect=make_conn
        ) as create_connection,
        # Keep it hermetic: don't spawn the router/ping/per-sub threads or send frames.
        patch.object(gql, "_conn_init"),
        patch.object(gql, "_subscription_loop"),
        patch.object(gql, "_start"),
    ):
        gql.subscribe("subscription { a }", callback=lambda _m: None)
        gql.subscribe("subscription { b }", callback=lambda _m: None)
        gql.subscribe("subscription { c }", callback=lambda _m: None)

    assert create_connection.call_count == 1, "all subscriptions share ONE socket"
    assert len(gql.subs) == 3, "all three subscriptions must be active"
    assert created[0].close.call_count == 0, (
        "the live shared connection must not be closed while subscriptions are active"
    )
    gql.closing = True
    Singleton._instances.pop(GraphQLClient, None)
