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
    if (msg['successful']):
        author = msg['result']
        print(f'author {author["name"]} was updated successfully')
    else:
        print(f'error creating author: {msg["messages"]}')


def on_author_created(msg):
    if (msg['successful']):
        author = msg['result']
        print(f'author {author["name"]} was created successfully')
    else:
        print(f'error creating author: {msg["messages"]}')


def test_subscribe_success(gql):
    sub_id = str(gql.sub_counter + 1)
    unsub_1 = gql.subscribe(subs.sub_author_created,
                            callback=on_author_created)
    assert type(unsub_1) == types.FunctionType, \
        'subscribe should return an unsubscribe function'
    assert len(gql.subs.items()) > 0, \
        'There should be at least ONE subscription active'
    assert gql.subs.get(sub_id) is not None, \
        'The subscription did not start with the correct ID'


def test_sub_routing_loop_message(gql):
    sub_id = str(gql.sub_counter + 1)
    _ = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
    runs = gql.subs[sub_id]['runs']
    # * This should activate the subscription at least once:
    _ = gql.mutate(muts.update_any_author_active, {
                   'name': 'Elon', 'lastname': 'Musk', 'active': True})
    _ = gql.mutate(muts.update_any_author_active, {
                   'name': 'Elon', 'lastname': 'Musk', 'active': False})
    # ! We don't know how long will it take for the server to respond to the subscription:
    sub_triggered = False
    elapsed = 0
    timeout = 5.0  # * Max seconds to wait
    startTime = time.time()
    while not sub_triggered and elapsed < timeout:
        new_runs = gql.subs[sub_id]['runs']
        sub_triggered = new_runs > runs
        time.sleep(0.01)  # * Give time to de server to react to the request
        elapsed = time.time() - startTime
    assert sub_triggered, \
        'Subscription should be triggered at least once'


def test_sub_default_callback(gql):
    sub_id = str(gql.sub_counter + 1)
    # * This adds coverage into the default callback
    _ = gql.subscribe(subs.sub_author_updated)
    runs = gql.subs[sub_id]['runs']
    # * This should activate the subscription at least once:
    _ = gql.mutate(muts.update_any_author_active, {
                   'name': 'Elon', 'lastname': 'Musk', 'active': True})
    _ = gql.mutate(muts.update_any_author_active, {
                   'name': 'Elon', 'lastname': 'Musk', 'active': False})
    # ! We don't know how long will it take for the server to respond to the subscription:
    sub_triggered = False
    elapsed = 0
    timeout = 5.0  # * Max seconds to wait
    startTime = time.time()
    while not sub_triggered and elapsed < timeout:
        new_runs = gql.subs[sub_id]['runs']
        sub_triggered = new_runs > runs
        time.sleep(0.01)  # * Give time to de server to react to the request
        elapsed = time.time() - startTime
    assert new_runs > runs, \
        'Subscription should be triggered at least once with default callback'
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
    gql.addEnvironment('routing-test', url='http://ex', wss='ws://ex', default=True)
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
    gql._conn.recv.return_value = b'null'

    with patch.object(gql, '_new_conn', side_effect=_stop_loop_on(gql)) as new_conn, \
            _capture_logs() as records:
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(level == LogLevel.WARNING and 'invalid WSS message' in msg
               for level, msg in records)
    assert not any(level == LogLevel.ERROR for level, msg in records)


def test_sub_routing_loop_connection_reset_logged_as_warning(routing_client):
    """OPS-3485: ConnectionResetError from recv is transient — log at WARNING (not
    ERROR+traceback) and halt for reconnection."""
    gql = routing_client
    gql._conn.recv.side_effect = ConnectionResetError(104, 'Connection reset by peer')

    with patch.object(gql, '_new_conn', side_effect=_stop_loop_on(gql)) as new_conn, \
            _capture_logs() as records:
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(level == LogLevel.WARNING and 'reset or closed by peer' in msg
               for level, msg in records)
    assert not any(level == LogLevel.ERROR and 'Some error trying to receive WSS' in msg
                   for level, msg in records)


def test_sub_routing_loop_unexpected_error_logged_as_error(routing_client):
    """A non-transient error (not in TRANSIENT_WS_ERRORS) must still surface at ERROR
    level and halt for reconnection."""
    gql = routing_client
    gql._conn.recv.side_effect = ValueError('unexpected wire failure')

    with patch.object(gql, '_new_conn', side_effect=_stop_loop_on(gql)) as new_conn, \
            _capture_logs() as records:
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is True
    assert new_conn.called
    assert any(level == LogLevel.ERROR and 'Some error trying to receive WSS' in msg
               for level, msg in records)


def test_sub_routing_loop_valid_message_does_not_halt(routing_client):
    """Regression: a well-formed dict message routes normally without halting or
    triggering reconnection."""
    gql = routing_client

    def _recv_then_close():
        gql.closing = True
        return b'{"type":"pong"}'

    gql._conn.recv.side_effect = _recv_then_close

    with patch.object(gql, '_new_conn') as new_conn, _capture_logs() as records:
        _run_routing_loop(gql)

    assert gql.wss_conn_halted is False
    new_conn.assert_not_called()
    assert not any(level == LogLevel.ERROR for level, msg in records)
    assert not any('invalid WSS message' in msg for level, msg in records)


def _seed_sub(gql, sub_id, **overrides):
    """Build a fully-shaped subscription entry and store it in gql.subs.

    The thread is started with a no-op target and immediately joined, so
    `.is_alive()` is False — exactly the post-mortem state we want to test
    the routing/registry against.
    """
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    sub = {
        'thread': thread,
        'queue': [],
        'runs': 0,
        'flatten': True,
        'query': 'subscription S { x }',
        'variables': {'a': 1},
        'callback': MagicMock(),
        'on_error_callback': MagicMock(),
        'running': False,
        'kill': False,
        'starting': False,
        'remove': False,
        'unsub': lambda: None,
    }
    sub.update(overrides)
    gql.subs[sub_id] = sub
    return sub


def test_complete_retains_sub_for_resubscribe(routing_client):
    """T1: server-initiated COMPLETE must NOT remove the sub from the registry,
    so the next reconnect's _resubscribe_all restores it."""
    gql = routing_client
    sub = _seed_sub(gql, '1', queue=[{'id': '1', 'type': 'complete'}])

    gql._subscription_loop(sub['callback'], '1', sub['on_error_callback'])

    assert '1' in gql.subs, 'COMPLETE must not remove sub from registry'
    assert gql.subs['1']['running'] is False
    assert gql.subs['1']['remove'] is False

    with patch.object(gql, 'subscribe') as mocked_subscribe:
        gql._resubscribe_all()

    mocked_subscribe.assert_called_once_with(
        query='subscription S { x }',
        variables={'a': 1},
        callback=sub['callback'],
        on_error_callback=sub['on_error_callback'],
        flatten=True,
        _id='1',
    )


def test_user_unsubscribe_removes_and_resubscribe_skips(routing_client):
    """T2: explicit user _unsubscribe sets remove=True and _resubscribe_all
    must skip removed subs."""
    gql = routing_client
    _seed_sub(gql, '1')

    with patch.object(gql, '_stop', return_value=None):
        gql._unsubscribe('1')

    assert gql.subs['1']['remove'] is True
    assert gql.subs['1']['kill'] is True

    with patch.object(gql, 'subscribe') as mocked_subscribe:
        gql._resubscribe_all()

    mocked_subscribe.assert_not_called()


def test_error_marks_remove(routing_client):
    """T3: server ERROR sets remove=True (preserves prior delete semantics) and
    invokes on_error_callback once."""
    gql = routing_client
    error_msg = {'id': '1', 'type': 'error', 'payload': [{'message': 'boom'}]}
    ecb = MagicMock()
    sub = _seed_sub(gql, '1', queue=[error_msg], on_error_callback=ecb)

    gql._subscription_loop(sub['callback'], '1', ecb)

    assert gql.subs['1']['remove'] is True
    ecb.assert_called_once_with(error_msg)


def test_cleanup_deletes_only_remove_subs(routing_client):
    """T4: the routing loop's cleanup must delete only subs marked remove=True;
    a dead-thread sub with remove=False must be retained for resubscribe."""
    gql = routing_client
    _seed_sub(gql, 'keep', running=False, remove=False)
    _seed_sub(gql, 'drop', running=False, remove=True)

    gql._conn.recv.side_effect = ConnectionResetError(104, 'Connection reset by peer')

    with patch.object(gql, '_new_conn', side_effect=_stop_loop_on(gql)), \
            patch.object(gql, '_resubscribe_all'):
        _run_routing_loop(gql)

    assert 'keep' in gql.subs, 'sub without remove=True must be retained'
    assert 'drop' not in gql.subs, 'sub with remove=True must be deleted'


def test_connection_drop_resubscribes_all_active(routing_client):
    """T5: regression — on a connection drop with no per-sub complete/error,
    _resubscribe_all restores every active sub (this is what fails today)."""
    gql = routing_client
    sub_a = _seed_sub(gql, 'a', query='subscription A { x }', variables={'k': 'a'})
    sub_b = _seed_sub(gql, 'b', query='subscription B { y }', variables={'k': 'b'})

    with patch.object(gql, 'subscribe') as mocked_subscribe:
        gql._resubscribe_all()

    assert mocked_subscribe.call_count == 2
    by_id = {call.kwargs['_id']: call.kwargs for call in mocked_subscribe.call_args_list}
    assert by_id['a']['query'] == 'subscription A { x }'
    assert by_id['a']['variables'] == {'k': 'a'}
    assert by_id['a']['callback'] is sub_a['callback']
    assert by_id['a']['on_error_callback'] is sub_a['on_error_callback']
    assert by_id['a']['flatten'] is True
    assert by_id['b']['query'] == 'subscription B { y }'
    assert by_id['b']['variables'] == {'k': 'b'}
    assert by_id['b']['callback'] is sub_b['callback']
