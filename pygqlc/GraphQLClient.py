'''GraphQL client implementation

This module has the general purpose of defining the GraphQLClient class
and all its methods.

GQLResponse (type variable): [data[field(string)], errors[message(string),
 field?(string)]
'''
import traceback
import time
import threading
from functools import lru_cache
import websocket
import httpx
import pydash as py_
import orjson
import logging
from pygqlc.helper_modules.Singleton import Singleton
from tenacity import (
    retry,
    retry_if_result,
    stop_after_attempt,
    wait_random
)
from .MutationBatch import MutationBatch

# Set httpx logger to WARNING level to reduce HTTP request logs
logging.getLogger('httpx').setLevel(logging.WARNING)

GQL_WS_SUBPROTOCOL = "graphql-transport-ws"

# * Custom Exception class for GraphQL responses


class GQLResponseException(Exception):
    """Custom GraphQL exception for query/mutation execution errors.

    Attributes:
        status_code (int): HTTP status code of the response
        query (str): GraphQL query or mutation that caused the error
        variables (dict): Variables used in the query/mutation
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        query: str,
        variables: dict | None = None,
    ) -> None:
        # Initialize the normal exception with the message
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.query = query
        self.variables = variables


def is_ws_payloadErrors_msg(message):
    return bool(py_.get(message, 'payload.errors'))


def is_ws_connection_init_msg(message):
    data = py_.get(message, 'payload.data', {})
    if not data:
        return False  # may have an error, but is not connection init message
    keys = list(data.keys())
    if keys and data[keys[0]] is None:
        # this message is a connection init one,
        # with the shape: {data: {datumCreatedOrSomething: None}}
        return True
    return False


def has_errors(result):
    """This function checks if a GqlResponse has any errors.

    Args:
        result (GqlResponse):  [data, errors]

    Returns:
        (boolean): Returns `True` if a transaction has at least one error.
    """
    _, errors = result
    return bool(errors)


@lru_cache(maxsize=128)
def _data_flatten_cacheable(data_str, single_child):
    """Internal cacheable version of data_flatten using string representation of data.

    Args:
        data_str (str): String representation of data object
        single_child (bool): Whether to flatten if data has only one child

    Returns:
        The flattened data structure
    """
    data = orjson.loads(data_str)
    return _data_flatten_impl(data, single_child)


def _data_flatten_impl(data, single_child=False):
    """Implementation of data_flatten that works on data structures directly.

    Args:
        data (dict, list): The data of a GqlResponse.
        single_child (bool): Checks if the data has only one element.

    Returns:
        (dict): Returns a formatted data.
    """
    if isinstance(data, dict):
        keys = list(data.keys())
        if len(keys) == 1:
            return _data_flatten_impl(data[keys[0]], single_child)
        else:
            return data  # ! various elements, nothing to flatten
    elif single_child and isinstance(data, list):
        if len(data) == 1:
            return _data_flatten_impl(data[0], single_child)
        elif len(data) == 0:
            return None  # * Return none if no child was found
        else:
            return data
    else:
        return data  # ! not a dict, nothing to flatten


def data_flatten(data, single_child=False):
    """This function formats the data structure of a GqlResponse.

    Args:
        data (dict, list): The data of a GqlResponse.
        single_child (bool, optional): Checks if the data has only one element.
        Defaults to False.

    Returns:
        (dict): Returns a formatted data.
    """
    if data is None:
        return None

    # For simple types or non-serializable objects, use direct implementation
    if isinstance(data, (str, int, float, bool)) or not isinstance(data, (dict, list)):
        return data

    try:
        # For cacheable data structures, use the cached version with orjson
        # orjson doesn't have sort_keys parameter, but has OPT_SORT_KEYS option
        data_str = orjson.dumps(
            data, option=orjson.OPT_SORT_KEYS).decode('utf-8')
        return _data_flatten_cacheable(data_str, single_child)
    except (TypeError, ValueError):
        # Fall back to direct implementation for non-serializable data
        return _data_flatten_impl(data, single_child)


def safe_pop(data, index=0, default=None):
    """This function pops safetly a GqlResponse from a subscription queue.

    Args:
        data (list): Is the list of GqlResponse that caught the subscription.
        index (int, optional): Index of the subscription queue. Defaults to 0.
        default (None, optional): Define the default message. Defaults to None.

    Returns:
        [GqlResponse]: Returns the GqlResponse. If the subscription queue is
         empty, it returns the default message.
    """
    if data:
        return data.pop(index)
    else:
        return default


# Prepare common JSON structures for reuse
PING_JSON = orjson.dumps({'type': 'ping'}).decode('utf-8')
CONNECTION_ACK_TYPE = 'connection_ack'
PONG_TYPE = 'pong'
NEXT_TYPE = 'next'
ERROR_TYPE = 'error'
COMPLETE_TYPE = 'complete'


class GraphQLClient(metaclass=Singleton):
    """The GraphQLClient class follows the singleton design pattern. It can
    make a query, mutation or subscription from an api.

    Attributes:
        environments (dict): Dictonary with all envieroments. Defaults to
          empty dict.
        environment (dict): Dictionary with the data of the actual enviroment.
          Defaults to None.
        ws_url (string): String with the WSS url. Defaults to None.
        subs (dict): Dictionary with all active subscriptions in the instance.
          Defaults to empty dict.
        sub_counter (int): Count of active subscriptions in the instance.
          Defaults to 0.
        sub_router_thread (thread): Thread with all subscription logic.
          Defaults to None.
        wss_conn_halted (boolean): Checks if the wss connection is halted.
          Defaults to False.
        closing (boolean): Checks if all subscriptions were successfully closed.
          Defaults to False.
        unsubscribing (boolean): Checks if all subscriptions were successfully
          canceled. Defaults to False.
        websocket_timeout (int): seconds of the websocket timeout. Defaults to
          60.

    Examples:
        >>> <With> clause:
          '''
          client = GraphQLClient()
          with client.enterEnvironment('dev') as gql:
              data, errors = gql.query('{lines(limit:2){id}}')
              # Process data and errors here
          '''
        >>> setEnvironment:
          '''
          client = GraphQLClient()
          client.addEnvironment('dev', "https://heineken.valiot.app/")
          client.addHeader(
              environment='dev',
              header={'Authorization': dev_token})
          data, errors = gql.query('{lines(limit:2){id}}')
          # Process data and errors here
          '''
    """

    # Reusable headers
    DEFAULT_HEADERS = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    def __init__(self):
        """Constructor of the GraphQlClient object.
        """
        # * query/mutation related attributes
        self.environments = {}
        self.environment = None
        # * wss/subscription related attributes:
        self.ws_url = None
        self._conn = None
        self.ack_timeout = 5
        self._subscription_running = False
        self.subs = {}  # * subscriptions running
        self.sub_counter = 0
        self.sub_router_thread = None
        self.sub_pingpong_thread = None
        self.wss_conn_halted = False
        self.closing = False
        self.unsubscribing = False
        self.websocket_timeout = 60
        self.pingIntervalTime = 15
        self.pingTimer = time.time()

        # Setup common client parameters
        self.client_params = {"http2": True}
        self.async_client_params = {"http2": True}

        # Reuse HTTP client for better performance
        self._http_client = None
        self._thread_local = threading.local()
        self._async_client = None

        # Configure sleep time for polling loops
        self.poll_interval = 0.005  # reduced from 0.01 for faster response

    # * with <Object> implementation
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.environment = self.save_env  # restores environment
        return

    def enterEnvironment(self, name):
        """This function makes a safe access to an environment.

        Args:
            name (string): Name of the environment.

        Returns:
            (self): Returns self instance for the use with `with` keyword.
        """
        self.save_env = self.environment
        self.environment = name
        return self  # * for use with "with" keyword

    # * HIGH LEVEL METHODS ---------------------------------
    # TODO: Implement tenacity in query, mutation and subscription methods
    # @retry(
    #   retry=(retry_if_result(has_errors)),
    #   stop=stop_after_attempt(5),
    #   wait=wait_random(min=0.25, max=0.5))
    # def query_wrapper(self, query, variables=None):
    #   data = None
    #   errors = []
    #   try:
    #     result = self.execute(query, variables)
    #     data = result.get('data', None)
    #     errors = result.get('errors', [])
    #   except Exception as e:
    #     errors = [{'message': str(e)}]
    #   return data, errors

    # * Query high level implementation
    def query(
        self,
        query: str,
        variables: dict | None = None,
        flatten: bool = True,
        single_child: bool = False
    ) -> tuple:
        """This function makes a query transaction to the actual environment.

        Args:
            query (string): GraphQL query instructions.
            variables (string, optional): Query variables. Defaults to None.
            flatten (bool, optional): Check if GraphQLResponse should be flatten or
             not. Defaults to True.
            single_child (bool, optional): Check if GraphQLResponse only has one
             element. Defaults to False.

        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        data = None
        errors = []
        try:
            response = self.execute(query, variables)
            if flatten:
                data = response.get('data', None)
            else:
                data = response
            errors = response.get('errors', [])
            if flatten and data is not None:
                data = data_flatten(data, single_child=single_child)
        except Exception as e:
            errors = [{'message': str(e)}]
        return data, errors

    # * Query high level implementation
    def query_one(self, query: str, variables: dict | None = None) -> tuple:
        """This function makes a single child query.

        Args:
            query (string): GraphQL query instructions.
            variables (string, optional): Query variables. Defaults to None.


        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        return self.query(query, variables, flatten=True, single_child=True)

    # * Mutation high level implementation
    def mutate(self, mutation: str, variables: dict | None = None, flatten: bool = True) -> tuple:
        """This function makes a mutation transaction to the actual environment.

        Args:
            mutation (string): GraphQL mutation instructions.
            variables (string, optional): Mutation variables. Defaults to None.
            flatten (bool, optional): Check if GraphQLResponse should be flatten or
             not. Defaults to True.

        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        response = {}
        data = None
        errors = []
        try:
            response = self.execute(mutation, variables)
        except Exception as e:
            errors = [{'message': str(e)}]
        finally:
            response_errors = response.get('errors', [])
            if response_errors:
                errors.extend(response_errors)
            if not errors:
                data = response.get('data', None)
                if flatten and data:
                    data = data_flatten(data)
                    data_messages = data.get('messages', []) if data else []
                    if data_messages:
                        errors.extend(data_messages)
        return data, errors

    # * Subscription high level implementation ******************

    def subscribe(
        self,
        query,
        variables=None,
        callback=None,
        flatten=True,
        _id=None,
        on_error_callback=None
    ):
        """This functions makes a subscription to the actual environment.

        Args:
            query (string): Graphql subscription instructions.
            variables (string, optional): Subscription variables. Defaults to None.
            callback (function, optional): Trigger function of the subscription.
             Defaults to None.
            flatten (bool, optional): Check if GraphqlResponse should be flatten or
             not. Defaults to True.
            _id (int, optional): Subscription id. Defaults to None.

        Returns:
            (GraphqlResponse): Returns the GraphqlResponse of the subscription.
        """
        # ! initialize websocket only once
        if not self._conn:
            if not self._new_conn():
                print('Error creating WSS connection for subscription')
                return None

        _cb = callback if callback is not None else self._on_message
        _ecb = on_error_callback
        _id = self._registerSub(_id)
        self.subs[_id].update({
            'thread': threading.Thread(target=self._subscription_loop, args=(_cb, _id, _ecb)),
            'flatten': flatten,
            'queue': [],
            'runs': 0,
            'query': query,
            'variables': variables,
            'callback': callback,
            'on_error_callback': on_error_callback
        })
        self.subs[_id]['thread'].start()
        payload = {'query': query, 'variables': variables}
        self._start(payload, _id)
        # ! Create unsubscribe function for this specific thread:

        def unsubscribe():
            return self._unsubscribe(_id)
        self.subs[_id].update({'unsub': unsubscribe})
        return unsubscribe

    def _unsubscribe(self, _id):
        sub = self.subs.get(_id)
        if not sub:
            print('Subscription already cleared')
            return
        self.unsubscribing = True
        sub['kill'] = True
        try:
            self._stop(_id)
        except BrokenPipeError as e:
            print('WSS Pipe broken, nothing to stop')
            print(f'original message: {e}')
        sub['thread'].join()
        sub['running'] = False
        self.unsubscribing = False

    def _sub_routing_loop(self):
        print('first subscription, starting routing loop')
        last_reconnect_attempt = 0
        reconnect_delay = 1.0

        while not self.closing:
            if self.wss_conn_halted:
                # Rate limit reconnection attempts
                current_time = time.time()
                if current_time - last_reconnect_attempt >= reconnect_delay:
                    print('Connection halted, attempting reconnection...')
                    if self._new_conn():
                        self.wss_conn_halted = False
                        print(
                            'WSS Reconnection succeeded, attempting resubscription to lost subs')
                        self._resubscribe_all()
                        print('finished resubscriptions')
                        reconnect_delay = 1.0  # Reset delay on success
                    else:
                        # Use exponential backoff for reconnection attempts (up to 5 seconds)
                        reconnect_delay = min(reconnect_delay * 1.5, 5.0)
                    last_reconnect_attempt = current_time
                time.sleep(self.poll_interval)
                continue

            if self.unsubscribing:
                time.sleep(self.poll_interval)
                continue

            # Process terminated subscriptions
            to_del = []
            for sub_id, sub in self.subs.items():
                if (sub['kill'] or not sub['running']) and not sub['starting']:
                    # Don't block if thread is already dead
                    if sub['thread'].is_alive():
                        # Use timeout to avoid blocking indefinitely
                        sub['thread'].join(0.1)
                    to_del.append(sub_id)

            for sub_id in to_del:
                del self.subs[sub_id]

            try:
                # Set a smaller timeout for faster response
                self._conn.settimeout(0.5)
                message = orjson.loads(self._conn.recv())
                # Reset timeout after successful receive
                self._conn.settimeout(self.websocket_timeout)
            except (TimeoutError, websocket.WebSocketTimeoutException):
                # Expected timeout - not an error
                time.sleep(self.poll_interval)
                continue
            except Exception as e:
                if not self.closing:
                    print(f'Some error trying to receive WSS')
                    print(f'original message: {e}')
                    self.wss_conn_halted = True
                continue

            message_type = message.get('type')
            if 'id' in message:
                # if the message has an ID request, it will be handled by the _subscription_loop
                _id = message['id']
                active_sub = self.subs.get(_id)
                # the connection may not be active due to:
                # 1. server error (incorrect ID sent)
                # 2. race condition (we closed connection, but a message was already on its way)
                if active_sub:
                    active_sub['queue'].append(message)
            elif message_type == CONNECTION_ACK_TYPE:
                pass  # Connection Ack with the server
            elif message_type == PONG_TYPE:
                pass
            else:
                print(f'unknown msg type: {message}')

            # Use non-blocking sleep
            time.sleep(self.poll_interval)

    def _resubscribe_all(self):
        # Copy subscription info before killing threads
        old_subs = {sub_id: {
            'query': sub.get('query'),
            'variables': sub.get('variables'),
            'callback': sub.get('callback'),
            'on_error_callback': sub.get('on_error_callback'),
            'flatten': sub.get('flatten'),
        } for sub_id, sub in self.subs.items()}

        # First, signal all threads to stop
        for sub in self.subs.values():
            sub['kill'] = True

        # Then join all threads with timeout to avoid blocking indefinitely
        for sub_id, sub in self.subs.items():
            if sub['thread'].is_alive():
                sub['thread'].join(0.5)

        # Clear existing subscriptions
        self.subs.clear()

        # Resubscribe using the saved information
        for sub_id, sub_info in old_subs.items():
            self.subscribe(
                query=sub_info['query'],
                variables=sub_info['variables'],
                callback=sub_info['callback'],
                on_error_callback=sub_info['on_error_callback'],
                flatten=sub_info['flatten'],
                _id=sub_id,
            )

    def _subscription_loop(self, _cb, _id, _ecb):
        self.subs[_id].update({'running': True, 'starting': False})
        while self.subs[_id]['running']:
            if self.subs[_id]['kill']:
                print(f'stopping subscription id={_id} on Unsubscribe')
                break

            # Get message without copying the queue
            message = safe_pop(self.subs[_id]['queue'])
            if not message:
                time.sleep(self.poll_interval)
                continue

            # Message type handling
            message_type = message.get('type')
            if message_type == NEXT_TYPE:
                pass  # continue with payload handling
            elif message_type == ERROR_TYPE:
                if _ecb:
                    _ecb(message)
                print(f'stopping subscription id={_id} on {message_type}')
                break
            elif message_type == COMPLETE_TYPE:
                print(f'stopping subscription id={_id} on {message_type}')
                break
            else:
                print(f'unknown msg type: {message}')
                continue

            # Payload handling
            if is_ws_payloadErrors_msg(message):
                if _ecb:
                    _ecb(message)
                    continue
                print('Subscription message has payload Errors')
                print(message)
            elif is_ws_connection_init_msg(message):
                # Subscription successfully initialized
                pass
            else:
                # Process message more efficiently
                gql_msg = self._clean_sub_message(_id, message)
                try:
                    _cb(gql_msg)  # execute callback function
                    # Increment counter without locking
                    self.subs[_id]['runs'] += 1
                except Exception as e:
                    print(f'Error on subscription callback: {e}')
                    sub_query = self.subs[_id].get('query')
                    sub_variables = self.subs[_id].get('variables')
                    if sub_query:
                        print(f'subscription document: \n\t{sub_query}')
                    if sub_variables:
                        print(f'subscription variables: \n\t{sub_variables}')
                    print(traceback.format_exc())

        # Subscription stopped, update state atomically
        self.subs[_id].update({'running': False, 'kill': True})
        print(f'Subscription id={_id} stopped')

    def _clean_sub_message(self, _id, message):
        data = py_.get(message, 'payload', {})
        return data_flatten(data) if self.subs[_id]['flatten'] else data

    def _new_conn(self):
        env = self.environments.get(self.environment, None)
        self.ws_url = env.get('wss')
        try:
            self._conn = websocket.create_connection(
                self.ws_url, subprotocols=[GQL_WS_SUBPROTOCOL])
            self._conn_init()
            return True
        except Exception as e:
            print(f'Failed connecting to {self.ws_url}')
            print(f'original message: {e}')
            return False

    def close(self):
        """This function ends and resets all subscriptions and related attributes
         to their default values.
        """
        # ! ask subscription message router to stop
        self.closing = True
        if not self.sub_router_thread:
            print('connection not stablished, nothing to close')
            self.closing = False
            return
        for sub in self.subs.values():
            sub['unsub']()
        self._conn.close()
        self.sub_router_thread.join()
        self.sub_pingpong_thread.join()
        self.sub_router_thread = None
        self.sub_pingpong_thread = None
        self._conn = None
        self.sub_counter = 0
        self.subs = {}
        self.closing = False

    def _on_message(self, message):
        '''Dummy callback for subscription'''
        # Message handling happens elsewhere - no need to print here
        pass

    def _conn_init(self):
        env = self.environments.get(self.environment, None)
        headers = env.get('headers', {})
        payload = {
            'type': 'connection_init',
            'payload': headers
        }
        self._conn.send(orjson.dumps(payload).decode('utf-8'))
        self._waiting_connection_ack()
        self._conn.settimeout(self.websocket_timeout)

        if not self.sub_router_thread:
            self.sub_router_thread = threading.Thread(
                target=self._sub_routing_loop)
        if not self.sub_router_thread.is_alive():
            self.sub_router_thread.start()
        if not self.sub_pingpong_thread:
            self.sub_pingpong_thread = threading.Thread(target=self._ping_pong)
        if not self.sub_pingpong_thread.is_alive():
            self.sub_pingpong_thread.start()

    def _waiting_connection_ack(self):
        self._conn.settimeout(self.ack_timeout)
        # set timeout to raise Exception websocket.WebSocketTimeoutException
        message = orjson.loads(self._conn.recv())
        if message['type'] == CONNECTION_ACK_TYPE:
            pass  # Connection Ack with the server

    def _ping_pong(self):
        self.pingTimer = time.time()
        ping_count = 0

        while not self.closing:
            time.sleep(0.1)
            if self.wss_conn_halted:
                continue

            current_time = time.time()
            if (current_time - self.pingTimer) > self.pingIntervalTime:
                self.pingTimer = current_time
                try:
                    self._conn.send(PING_JSON)
                    ping_count += 1
                    # No need to log normal ping operations
                except Exception as e:
                    if not self.closing:
                        print('error trying to send ping, WSS Pipe is broken')
                        print(f'original message: {e}')
                        self.wss_conn_halted = True

    def _registerSub(self, _id=None):
        if not _id:
            self.sub_counter += 1
            _id = str(self.sub_counter)
        self.subs[_id] = {'running': False, 'kill': False, 'starting': True}
        return _id

    def _start(self, payload, _id):
        frame = {'id': _id, 'type': 'subscribe', 'payload': payload}
        self._conn.send(orjson.dumps(frame).decode('utf-8'))

    def _stop(self, _id):
        payload = {'id': _id, 'type': 'complete'}
        self._conn.send(orjson.dumps(payload).decode('utf-8'))

    def resetSubsConnection(self):
        """This function resets all subscriptions connections.

        Returns:
            (boolean): Returns if the reconnection has been possible.
        """
        if not self.sub_router_thread:
            print('connection not stablished, nothing to reset')
            return False
        if self.sub_router_thread.is_alive():  # check that _sub_routing_loop() is running
            self._conn.close()  # forces connection halted (wss_conn_halted)
            return True
        # in case for some reason _sub_routing_loop() is not running
        if self._new_conn():
            print('WSS Reconnection succeeded, attempting resubscription to lost subs')
            self._resubscribe_all()
            print('finished resubscriptions')
            return True
        else:
            print('Reconnection has not been possible')
            return False

    # * END SUBSCRIPTION functions ******************************

    # * BATCH functions *****************************************
    def batchMutate(self, label='mutation'):
        """This fuction makes a batchs of mutation transactions.

        Args:
            label (str, optional): Name of the mutation batch. Defaults to 'mutation'.

        Returns:
            (MutationBatch): Returns a MutationBatch Object.
        """
        return MutationBatch(client=self, label=label)

    def batchQuery(self, label='query'):
        """This fuction makes a batchs of query transactions.

        Args:
            label (str, optional): Name of the query batch. Defaults to 'query'.

        Returns:
            (MutationBatch): Returns a MutationBatch Object.
        """
        return MutationBatch(client=self, label=label)

    # * END BATCH function **************************************
    # * helper methods
    def addEnvironment(
        self,
        name,
        url=None,
        wss=None,
        headers={},
        default=False,
        timeoutWebsocket=60,
        post_timeout=60,
        ipv4_only=False
    ):
        """This fuction adds a new environment to the instance.

        Args:
            name (string): Name of the environment.
            url (string, optional): URL of the environmet. Defaults to None.
            wss (string, optional): URL of the WSS of the environment. Defaults to None.
            headers (dict, optional): A dictionary with the headers
             (like authorization). Defaults to {}.
            default (bool, optional): Checks if the new environment will be the
             default one of the instance. Defaults to False.
            timeoutWebsocket (int, optional): Seconds of the timeout of the
             websocket. Defaults to 60.
            post_timeout (int, optional): Timeout in seconds for each post.
             Defaults to 60.
            ipv4_only (bool, optional): Forces connections to use IPv4 only.
             Helps with slow connections on networks with problematic IPv6. Defaults to False.
        """
        self.environments[name] = {
            'url': url,
            'wss': wss,
            'headers': headers.copy(),
            'post_timeout': post_timeout,
            'ipv4_only': ipv4_only
        }

        if ipv4_only:
            self._update_client_params(ipv4_only)

        if default:
            self.setEnvironment(name)
        self.setTimeoutWebsocket(timeoutWebsocket)

    def _update_client_params(self, ipv4_only):
        """Update HTTP client parameters based on IPv4 setting"""
        if ipv4_only:
            self.client_params["transport"] = httpx.HTTPTransport(
                local_address="0.0.0.0")
            self.async_client_params["transport"] = httpx.AsyncHTTPTransport(
                local_address="0.0.0.0")
        else:
            # Remove transport if it exists
            self.client_params.pop("transport", None)
            self.async_client_params.pop("transport", None)

    def setUrl(self, environment=None, url=None):
        """This function sets a new url to an existing environment.

        Args:
            environment (string, optional): Name of the environment. Defaults to None.
            url (string, optional): New URL for the enviroment. Defaults to None.
        """
        # if environment is not selected, use current environment
        if not environment:
            environment = self.environment
        self.environments[environment]['url'] = url

    def setWss(self, environment=None, url=None):
        """This function sets a new WSS to an existing environment.

        Args:
            environment (string, optional): Name of the environment. Defaults to None.
            url (string, optional): New WSS URL for the environment. Defaults to None.
        """
        # if environment is not selected, use current environment
        if not environment:
            environment = self.environment
        self.environments[environment]['wss'] = url

    def addHeader(self, environment=None, header={}):
        """This function updates the header of an existing environment.

        Args:
            environment (string, optional): Name of the environment. Defaults to None.
            header (dict, optional): New headers to add. Defaults to {}.
        """
        # if environment is not selected, use current environment
        if not environment:
            environment = self.environment
        self.environments[environment]['headers'].update(header)

    def setEnvironment(self, name):
        """This functions sets the actual environment of the instance.

        Args:
            name (string): Name of the environment.

        Raises:
            Exception: The environment's name doesn't exists in the environment list.
        """
        env = self.environments.get(name)
        if not env:
            raise Exception(f'selected environment not set ({name})')
        self.environment = name

        # Update client parameters based on environment settings
        ipv4_only = env.get('ipv4_only', False)
        self._update_client_params(ipv4_only)

    def setPostTimeout(self, environment=None, post_timeout=60):
        """This function sets the post's timeout.

        Args:
            seconds (int): Time for the timeout.
        """
        # if environment is not selected, use current environment
        if not environment:
            environment = self.environment
        self.environments[environment]['post_timeout'] = post_timeout

    def setTimeoutWebsocket(self, seconds):
        """This function sets the webscoket's timeout.

        Args:
            seconds (int): Time for the timeout.
        """
        self.websocket_timeout = seconds
        if self._conn:
            self._conn.settimeout(self.websocket_timeout)

    # * LOW LEVEL METHODS ----------------------------------
    def _get_http_client(self):
        """Get a thread-local HTTP client to improve performance with connection pooling"""
        if not hasattr(self._thread_local, 'client'):
            self._thread_local.client = httpx.Client(**self.client_params)
        return self._thread_local.client

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """This function executes the intructions of a query or mutation.

        Args:
            query (string): GraphQL instructions.
            variables (string, optional): Variables of the transaction. Defaults
             to None.

        Raises:
            Exception: There is not setted a main environment.
            GQLResponseException: Raised when the GraphQL query fails.

        Returns:
            dict: Raw GraphQLResponse.
        """
        data = {
            'query': query,
            'variables': variables
        }
        env = self.environments.get(self.environment)
        if not env:
            raise Exception(
                f'cannot execute query without setting an environment')

        headers = self.DEFAULT_HEADERS.copy()
        env_headers = env.get('headers')
        if env_headers:
            headers.update(env_headers)

        # Use thread-local client for better connection pooling
        try:
            client = self._get_http_client()
            response = client.post(
                env['url'],
                json=data,
                headers=headers,
                timeout=float(env.get('post_timeout', 60))
            )
        except Exception as e:
            # If connection fails, create a new client and retry
            self._thread_local.client = httpx.Client(**self.client_params)
            client = self._thread_local.client
            response = client.post(
                env['url'],
                json=data,
                headers=headers,
                timeout=float(env.get('post_timeout', 60))
            )

        if response.status_code == 200:
            return orjson.loads(response.content)
        else:
            error_message = "Query failed to run by returning code of " + \
                f"{response.status_code}.\n{query}"
            raise GQLResponseException(
                message=error_message,
                status_code=response.status_code,
                query=query,
                variables=variables
            )

    # * ASYNC METHODS ----------------------------------
    async def _get_async_client(self):
        """Get or create a reusable async HTTP client for better performance

        Detects if the event loop has been closed (which can happen in test environments)
        and creates a new client if necessary.
        """
        new_client_needed = False

        # Check if client exists
        if self._async_client is None:
            new_client_needed = True
        else:
            # Check if client's event loop is closed
            try:
                # Make a simple request to check if client is still usable
                # This will fail with "Event loop is closed" if the loop is closed
                await self._async_client.get_timeout()
            except (RuntimeError, AttributeError) as e:
                if "Event loop is closed" in str(e) or "has no attribute" in str(e):
                    # Event loop closed or client has been partially destroyed
                    # Create a new client
                    new_client_needed = True
                    # Intentionally don't try to close the old client as its event loop is closed
                    self._async_client = None
                else:
                    # Some other error, re-raise
                    raise

        # Create a new client if needed
        if new_client_needed:
            self._async_client = httpx.AsyncClient(**self.async_client_params)

        return self._async_client

    async def _close_async_client(self):
        """Close the async client if it exists"""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    async def async_execute(self, query: str, variables: dict | None = None) -> dict:
        """Async version of execute method that executes instructions of a query or mutation.

        Args:
            query (string): GraphQL instructions.
            variables (string, optional): Variables of the transaction. Defaults
             to None.

        Raises:
            Exception: There is not setted a main environment.
            GQLResponseException: Raised when the GraphQL query fails.

        Returns:
            dict: Raw GraphQLResponse.
        """
        data = {
            'query': query,
            'variables': variables
        }
        env = self.environments.get(self.environment)
        if not env:
            raise Exception(
                f'cannot execute query without setting an environment')

        headers = self.DEFAULT_HEADERS.copy()
        env_headers = env.get('headers')
        if env_headers:
            headers.update(env_headers)

        # Get a client that we know is connected to a valid event loop
        client = await self._get_async_client()

        try:
            # Make the actual request
            response = await client.post(
                env['url'],
                json=data,
                headers=headers,
                timeout=float(env.get('post_timeout', 60))
            )
        except (httpx.RequestError, RuntimeError) as e:
            # Check if this is an event loop issue or a network issue
            if "Event loop is closed" in str(e):
                # Event loop was closed - need to get a new client with a valid loop
                # The _get_async_client method will handle this on the next call
                self._async_client = None
                # Try again with a new client
                client = await self._get_async_client()
                response = await client.post(
                    env['url'],
                    json=data,
                    headers=headers,
                    timeout=float(env.get('post_timeout', 60))
                )
            else:
                # Some other request error, re-raise
                raise

        if response.status_code == 200:
            return orjson.loads(response.content)
        else:
            error_message = "Query failed to run by returning code of " + \
                f"{response.status_code}.\n{query}"
            raise GQLResponseException(
                message=error_message,
                status_code=response.status_code,
                query=query,
                variables=variables
            )

    async def async_query(
        self,
        query: str,
        variables: dict | None = None,
        flatten: bool = True,
        single_child: bool = False
    ) -> tuple:
        """Async version of query method that makes a query transaction to the actual environment.

        Args:
            query (string): GraphQL query instructions.
            variables (string, optional): Query variables. Defaults to None.
            flatten (bool, optional): Check if GraphQLResponse should be flatten or
             not. Defaults to True.
            single_child (bool, optional): Check if GraphQLResponse only has one
             element. Defaults to False.

        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        data = None
        errors = []
        try:
            response = await self.async_execute(query, variables)
            if flatten:
                data = response.get('data', None)
            else:
                data = response
            errors = response.get('errors', [])
            if flatten and data is not None:
                data = data_flatten(data, single_child=single_child)
        except Exception as e:
            errors = [{'message': str(e)}]
        return data, errors

    async def async_query_one(self, query: str, variables: dict | None = None) -> tuple:
        """Async version of query_one method that makes a single child query.

        Args:
            query (string): GraphQL query instructions.
            variables (string, optional): Query variables. Defaults to None.

        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        return await self.async_query(query, variables, flatten=True, single_child=True)

    async def async_mutate(
            self,
            mutation: str,
            variables: dict | None = None,
            flatten: bool = True
    ) -> tuple:
        """Async version of mutate method that makes a mutation transaction
        to the current environment.

        Args:
            mutation (string): GraphQL mutation instructions.
            variables (string, optional): Mutation variables. Defaults to None.
            flatten (bool, optional): Check if GraphQLResponse should be flatten or
             not. Defaults to True.

        Returns:
            tuple: Tuple containing (data, errors) from the GraphQL response.
        """
        response = {}
        data = None
        errors = []
        try:
            response = await self.async_execute(mutation, variables)
        except Exception as e:
            errors = [{'message': str(e)}]
        finally:
            response_errors = response.get('errors', [])
            if response_errors:
                errors.extend(response_errors)
            if not errors:
                data = response.get('data', None)
                if flatten and data:
                    data = data_flatten(data)
                    data_messages = data.get(
                        'messages', []) if data else []
                    if data_messages:
                        errors.extend(data_messages)
        return data, errors

    # Ensure cleanup of resources
    async def async_cleanup(self):
        """Close any open async resources

        This method should only be called when you know no other
        async operations are in progress. It handles cases where
        the event loop might already be closed.
        """
        if self._async_client is not None:
            try:
                # Check if the client is still usable
                try:
                    # This will raise an exception if the event loop is closed
                    await self._async_client.get_timeout()
                    # If we get here, the client is usable, so close it
                    await self._async_client.aclose()
                except (RuntimeError, AttributeError) as e:
                    if "Event loop is closed" in str(e) or "has no attribute" in str(e):
                        # Client's event loop is already closed
                        # We can't await aclose(), just let it be garbage collected
                        pass
                    else:
                        # Some other error during check, still try to close
                        await self._async_client.aclose()
            except Exception as e:  # pylint: disable=broad-except
                # If closing fails, log but continue
                print(f"Warning: Error closing async client: {str(e)}")
            finally:
                # Always set to None to allow garbage collection and recreation
                self._async_client = None

    def _close(self):
        """Explicitly close resources"""
        # Clean up synchronous client
        if hasattr(self, '_thread_local') and hasattr(self._thread_local, 'client'):
            try:
                self._thread_local.client.close()
            except Exception:  # pylint: disable=broad-except
                pass

        # For async client, we can't use await in close(), so just set to None
        # to allow garbage collection. We don't try to close it properly here
        # as that would require an event loop, which might be closed already.
        if hasattr(self, '_async_client') and self._async_client is not None:
            self._async_client = None

    def __del__(self):
        """Cleanup resources when the instance is being destroyed"""
        self._close()
