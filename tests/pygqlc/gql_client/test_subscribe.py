from . import subscriptions as subs
from . import mutations as muts
import types
import time
from unittest.mock import MagicMock, patch


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


def test_sub_routing_loop_handles_connection_reset_and_invalid_messages():
    """TDD test for OPS-3485: _sub_routing_loop must not let ConnectionResetError
    (from ws recv on peer reset) or post-parse None/invalid messages escape and
    kill the routing thread. Invalid msgs after reset need guard.
    Write test first -> currently RED because AttributeError on None.get after loads('null').
    """
    from pygqlc import GraphQLClient
    import threading
    import time as _time
    import sys
    from io import StringIO

    gql = GraphQLClient()
    gql.addEnvironment('testenv', url='http://ex', wss='ws://ex', default=True)

    # --- Scenario 1: invalid message (loads to None) causes AttributeError on .get today ---
    mock_conn = MagicMock()
    mock_conn.recv.return_value = b'null'  # orjson.loads -> None ; then .get crashes outside try
    mock_conn.settimeout.return_value = None
    mock_conn.close.return_value = None

    gql._conn = mock_conn
    gql.wss_conn_halted = False
    gql.closing = False
    gql.unsubscribing = False
    gql.subs = {}
    gql.poll_interval = 0.001
    gql.websocket_timeout = 1

    old_stderr = sys.stderr
    sys.stderr = mystd = StringIO()
    try:
        thread = threading.Thread(target=gql._sub_routing_loop, daemon=True)
        thread.start()
        _time.sleep(0.05)  # let it do one recv+crash
        gql.closing = True
        thread.join(timeout=0.5)
        stderr_content = mystd.getvalue()
    finally:
        sys.stderr = old_stderr

    # CURRENTLY RED: AttributeError from 'NoneType' has no 'get' will be in stderr or thread died unclean
    # After fix (guard after loads), no such error, thread survives the bad msg by setting halted
    has_crash = 'AttributeError' in stderr_content or "'NoneType' object has no attribute 'get'" in stderr_content
    assert not has_crash, "Expected no crash on invalid message after peer-reset-like data; got: " + stderr_content[:300]
    assert gql.wss_conn_halted, "Should set halted on invalid/None message to trigger reconnect"
    assert not thread.is_alive(), "routing thread must survive bad message"

    # --- Scenario 2: ConnectionResetError on recv is caught, sets halted, no escape ---
    mock_conn2 = MagicMock()
    reset_count = {'c': 0}

    def recv_reset():
        reset_count['c'] += 1
        if reset_count['c'] == 1:
            raise ConnectionResetError(104, "Connection reset by peer")
        gql.closing = True
        return b'{"type":"pong"}'

    mock_conn2.recv.side_effect = recv_reset
    mock_conn2.settimeout.return_value = None

    gql2 = GraphQLClient()
    gql2.addEnvironment('testenv2', url='http://ex', wss='ws://ex', default=True)
    gql2._conn = mock_conn2
    gql2.wss_conn_halted = False
    gql2.closing = False
    gql2.unsubscribing = False
    gql2.subs = {}
    gql2.poll_interval = 0.001
    gql2.websocket_timeout = 1

    # patch _new_conn so halted path doesn't try real connect and loop forever
    with patch.object(gql2, '_new_conn', return_value=False):
        thread2 = threading.Thread(target=gql2._sub_routing_loop, daemon=True)
        thread2.start()
        _time.sleep(0.1)
        gql2.closing = True
        thread2.join(timeout=0.5)

    assert not thread2.is_alive(), "thread must not die from ConnectionResetError"
    assert gql2.wss_conn_halted, "reset error must set halted for reconnection logic"
