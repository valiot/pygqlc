import requests
import json
import time
import threading
import websocket
import pydash as py_
from pygqlc.helper_modules.Singleton import Singleton
from tenacity import (
  retry, 
  retry_if_result, 
  stop_after_attempt, 
  wait_random
)
"""
This module has the general purpose of defining the GraphQLClient class
and all its methods.

GQLResponse (type variable): [data[field(string)], errors[message(string),
 field?(string)]

"""

from .MutationBatch import MutationBatch

GQL_WS_SUBPROTOCOL = "graphql-transport-ws"

def is_ws_payloadErrors_msg(message):
  errors = py_.get(message, 'payload.errors')
  if (errors):
    return True
  return False
  
def is_ws_connection_init_msg(message):
  data = py_.get(message, 'payload.data', {})
  if not data:
    return False # may have an error, but is not connection init message
  keys = list(data.keys())
  if (len(keys) > 0):
    body = data[keys[0]]
    if (body == None):
      return True # this message is a connection init one, with the shape: {data: {datumCreatedOrSomething: None}}
  return False

def has_errors(result):
  """This function checks if a GqlResponse has any errors.

  Args:
      result (GqlResponse):  [data, errors]

  Returns:
      (boolean): Returns `True` if a transaction has at least one error.
  """
  _, errors = result
  return len(errors) > 0


def data_flatten(data, single_child=False):
  """This function formats the data structure of a GqlResponse.

  Args:
      data (dict, list): The data of a GqlResponse.
      single_child (bool, optional): Checks if the data has only one element.
      Defaults to False.

  Returns:
      (dict): Returns a formatted data.
  """
  if type(data) == dict:
    keys = list(data.keys())
    if len(keys) == 1:
      key = list(data.keys())[0]
      return data_flatten(data[key], single_child)
    else:
      return data  # ! various elements, nothing to flatten
  elif single_child and type(data) == list:
    if len(data) == 1:
      return data_flatten(data[0], single_child)
    elif len(data) == 0:
      return None  # * Return none if no child was found
    else:
      return data
  else:
    return data  # ! not a dict, nothing to flatten


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
  if len(data) > 0:
    return data.pop(index)
  else:
    return default


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
            print(data, errors)
        '''
      >>> setEnvironment:
        '''
        client = GraphQLClient()
        client.addEnvironment('dev', "https://heineken.valiot.app/")
        client.addHeader(
            environment='dev',
            header={'Authorization': dev_token})
        data, errors = gql.query('{lines(limit:2){id}}')
        print(data, errors)
        '''
  """
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
    self.subs = {} # * subscriptions running
    self.sub_counter = 0
    self.sub_router_thread = None
    self.sub_pingpong_thread = None
    self.wss_conn_halted = False
    self.closing = False
    self.unsubscribing = False
    self.websocket_timeout = 60
    self.pingIntervalTime = 15
    self.pingTimer = time.time()
  
  # * with <Object> implementation
  def __enter__(self):
    return self
  
  def __exit__(self, type, value, traceback):
    self.environment = self.save_env # restores environment
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
    return self # * for use with "with" keyword
  
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
  def query(self, query, variables=None, flatten=True, single_child=False):
    """This function makes a query transaction to the actual environment.

    Args:
        query (string): Graphql query instructions.
        variables (string, optional): Query variables. Defaults to None.
        flatten (bool, optional): Check if GraphqlResponse should be flatten or
         not. Defaults to True.
        single_child (bool, optional): Check if GraphqlResponse only has one
         element. Defaults to False.

    Returns:
        (GraphqlResponse): Returns the GraphqlResponse of the query.
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
      if flatten:
        data = data_flatten(data, single_child=single_child)
    except Exception as e:
      errors = [{'message': str(e)}]
    return data, errors

  # * Query high level implementation
  def query_one(self, query, variables=None):
    """This function makes a single child query.

    Args:
        query (string): Graphql query instructions.
        variables (string, optional): Query variables. Defaults to None.


    Returns:
        (GraphqlResponse): Returns the GraphqlResponse of the query.
    """
    return self.query(query, variables, flatten=True, single_child=True)
  
  # * Mutation high level implementation
  def mutate(self, mutation, variables=None, flatten=True):
    """This function makes a mutation transaction to the actual environment.

    Args:
        mutation (string): Graphql mutation instructions.
        variables (string, optional): Mutation variables. Defaults to None.
        flatten (bool, optional): Check if GraphqlResponse should be flatten or
         not. Defaults to True.

    Returns:
        (GraphqlResponse): Returns the GraphqlResponse of the mutation.
    """
    response = {}
    data = None
    errors = []
    try:
      response = self.execute(mutation, variables)
    except Exception as e:
      errors = [{'message': str(e)}]
    finally:
      errors.extend(response.get('errors', []))
      if(not errors):
        data = response.get('data', None)
      if flatten:
        data = data_flatten(data)
        if (data):
          errors.extend(data.get('messages', []))
    return data, errors
  # * Subscription high level implementation ******************
  def subscribe(self, query, variables=None, callback=None, flatten=True, _id=None, on_error_callback=None ):
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
      if self._new_conn():
        pass # print('No connection found, created.')
      else:
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
    if not self.subs.get(_id):
      print('Subscription already cleared')
      return
    self.unsubscribing = True
    self.subs[_id]['kill'] = True
    try:
      self._stop(_id)
    except BrokenPipeError as e:
      print('WSS Pipe broken, nothing to stop')
      print(f'original message: {e}')
    self.subs[_id]['thread'].join()
    self.subs[_id].update({'running': False})
    self.unsubscribing = False
  
  def _sub_routing_loop(self):
    print('first subscription, starting routing loop')
    while not self.closing:
      if (self.wss_conn_halted):
        print('Connection halted, attempting reconnection...')
        if self._new_conn():
          self.wss_conn_halted = False
          print('WSS Reconnection succeeded, attempting resubscription to lost subs')
          self._resubscribe_all()
          print('finished resubscriptions')
        else:
          time.sleep(1.0)
          continue
      if self.unsubscribing:
        time.sleep(0.01)
        continue
      # this guy can handle unsubscriptions from another thread:
      to_del = []
      for sub_id, sub in self.subs.items():
        if sub['kill'] or not sub['running']:
          if sub['starting']: continue
          print(f'deleting halted subscription (id: {sub_id})')
          sub['thread'].join()
          to_del.append(sub_id)
      for sub_id in to_del:
        del self.subs[sub_id]
      try:
        message = json.loads(self._conn.recv())
      except (TimeoutError, websocket.WebSocketTimeoutException) as e:
        print('Timeout for WSS message exceeded...')
        print(f'original message: {e}')
        self.wss_conn_halted = True
        continue
      except Exception as e:
         print(f'Some error trying to receive WSS')
         print(f'original message: {e}')
         self.wss_conn_halted = True
         continue

      if 'id' in message.keys(): 
        # if the message has an ID request, it will be handled by the _subscription_loop
        _id = py_.get(message, 'id')
        active_sub = self.subs.get(_id)
        # the connection may not be active due to:
        # 1. server error (incorrect ID sent)
        # 2. race condition (we closed connection, but a message was already on its way here) 
        if (not active_sub):
          continue
        active_sub['queue'].append(message)
      elif message['type'] == 'connection_ack':
        print('Connection Ack with the server.')
        pass
      elif message['type'] == 'pong':
        pass
      else:
        print(f'unknown msg type: {message}')

      time.sleep(0.01)
  
  def _resubscribe_all(self):
    # first, clear every subscription thread running:
    for sub_id in self.subs.keys():
      self.subs[sub_id]['kill'] = True  # Signal threads to stop
    # wait for every thread to finish
    for sub_id in self.subs.keys():
      print(f'killing halted subscription (id={sub_id})')
      self.subs[sub_id]['thread'].join()
    # attempt re-join:
    old_subs = self.subs
    for sub_id in old_subs.keys():
      self.subscribe(
        query=old_subs[sub_id]['query'],
        variables=old_subs[sub_id]['variables'],
        callback=old_subs[sub_id]['callback'],
        on_error_callback=old_subs[sub_id]['on_error_callback'],
        flatten=old_subs[sub_id]['flatten'],
        _id=sub_id,
      )
  
  def _subscription_loop(self, _cb, _id, _ecb):
    self.subs[_id].update({'running': True, 'starting': False})
    while self.subs[_id]['running']:
      aborted = self.subs[_id]['kill']
      if aborted:
        print(f'stopping subscription id={_id} on Unsubscribe')
        break
      message = safe_pop(self.subs[_id]['queue'])
      if not message:
        time.sleep(0.01)
        continue

      # Message type handling
      if message['type'] == 'next':
        pass # continue with payload handling
      elif message['type'] == 'error':
        if _ecb: _ecb(message)
        print(f'stopping subscription id={_id} on {message["type"]}')
        break
      elif message['type'] == 'complete':
        print(f'stopping subscription id={_id} on {message["type"]}')
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
        print('Subscription successfully initialized')
      else:
        gql_msg = self._clean_sub_message(_id, message)
        _cb(gql_msg) # execute callback function
        self.subs[_id]['runs'] += 1 # take note of how many times this sub has been triggered   

      time.sleep(0.01)
    # ! subscription stopped, due to error or user event
    print(f'Subscription id={_id} stopped')
    self.subs[_id].update({'running': False, 'kill': True})
  
  def _clean_sub_message(self, _id, message):
    data = py_.get(message, 'payload', {})
    return data_flatten(data) if self.subs[_id]['flatten'] else data

  def _new_conn(self):
    env = self.environments.get(self.environment, None)
    self.ws_url = env.get('wss')
    try:
      self._conn = websocket.create_connection(self.ws_url, subprotocols=[GQL_WS_SUBPROTOCOL])
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
    for _, sub in self.subs.items():
      sub['unsub']()
    self.sub_router_thread.join()
    self.sub_pingpong_thread.join()
    self._conn.close()
    self.sub_router_thread = None
    self.sub_pingpong_thread = None
    self._conn = None
    self.sub_counter = 0
    self.subs = {}
    self.closing = False
  
  def _on_message(self, message):
    '''Dummy callback for subscription'''
    print(f'message received on subscription:')
    print(message)

  def _conn_init(self):
    env = self.environments.get(self.environment, None)
    headers = env.get('headers', {})
    payload = {
      'type': 'connection_init',
      'payload': headers
    }
    self._conn.send(json.dumps(payload))
    self._waiting_connection_ack()
    self._conn.settimeout(self.websocket_timeout)

    if not self.sub_router_thread:
      self.sub_router_thread = threading.Thread(target=self._sub_routing_loop)
    if not self.sub_router_thread.is_alive():
      self.sub_router_thread.start()
    if not self.sub_pingpong_thread:
      self.sub_pingpong_thread = threading.Thread(target=self._ping_pong)
    if not self.sub_pingpong_thread.is_alive():
      self.sub_pingpong_thread.start()

  def _waiting_connection_ack(self):
    self._conn.settimeout(self.ack_timeout)
    # set timeout to raise Exception websocket.WebSocketTimeoutException
    message = json.loads(self._conn.recv()) 
    if message['type'] == 'connection_ack':
      print('Connection Ack with the server.')

  def _ping_pong(self):
    self.pingTimer = time.time()
    while not self.closing:
      time.sleep(0.1)
      if self.wss_conn_halted:
        continue
      if ((time.time() - self.pingTimer) > self.pingIntervalTime):
        self.pingTimer = time.time()
        try:
          self._conn.send(json.dumps({ 'type': 'ping' }))
        except Exception as e:
          print('error trying to send ping, WSS Pipe is broken')
          print(f'original message: {e}')
          self.wss_conn_halted = True

  def _registerSub(self, _id=None):
    if not _id:
      self.sub_counter += 1
      _id = str(self.sub_counter)
    self.subs.update({_id: {'running': False, 'kill': False, 'starting': True}})
    return _id
      
  def _start(self, payload, _id):
    frame = {'id': _id, 'type': 'subscribe', 'payload': payload}
    self._conn.send(json.dumps(frame))

  def _stop(self, _id):
    payload = {'id': _id, 'type': 'complete'}
    self._conn.send(json.dumps(payload))

  def resetSubsConnection(self):
    """This function resets all subscriptions connections.

    Returns:
        (boolean): Returns if the reconnection has been possible.
    """
    if not self.sub_router_thread:
      print('connection not stablished, nothing to reset')
      return False
    if self.sub_router_thread.isAlive(): #check that _sub_routing_loop() is running
      self._conn.close() # forces connection halted (wss_conn_halted)
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
  def addEnvironment(self, name, url=None, wss=None, headers={}, default=False, timeoutWebsocket=60, post_timeout=60):
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
    """
    self.environments.update({
      name: {
        'url': url,
        'wss': wss,
        'headers': headers,
        'post_timeout': post_timeout
      }
    })
    if default:
      self.setEnvironment(name)
    self.setTimeoutWebsocket(timeoutWebsocket)

  def setUrl(self, environment=None, url=None):
    """This function sets a new url to an existing environment.

    Args:
        environment (string, optional): Name of the environment. Defaults to None.
        url (string, optional): New URL for the enviroment. Defaults to None.
    """
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments[environment].update({'url': url})
  
  def setWss(self, environment=None, url=None):
    """This function sets a new WSS to an existing environment.

    Args:
        environment (string, optional): Name of the environment. Defaults to None.
        url (string, optional): New WSS URL for the environment. Defaults to None.
    """
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments[environment].update({'wss': url})
  
  def addHeader(self, environment=None, header={}):
    """This function updates the header of an existing environment.

    Args:
        environment (string, optional): Name of the environment. Defaults to None.
        header (dict, optional): New headers to add. Defaults to {}.
    """
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    headers = self.environments[environment].get('headers', {})
    headers.update(header)
    self.environments[environment]['headers'].update(headers)

  def setEnvironment(self, name):
    """This functions sets the actual environment of the instance.

    Args:
        name (string): Name of the environment.

    Raises:
        Exception: The environment's name doesn't exists in the environment list.
    """
    env = self.environments.get(name, None)
    if not env:
      raise Exception(f'selected environment not set ({name})')
    self.environment = name

  def setPostTimeout(self, environment=None, post_timeout=60):
    """This function sets the post's timeout.

    Args:
        seconds (int): Time for the timeout.
    """
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments[environment].update({'post_timeout': post_timeout})

  
  def setTimeoutWebsocket(self, seconds):
    """This function sets the webscoket's timeout.

    Args:
        seconds (int): Time for the timeout.
    """
    self.websocket_timeout =  seconds
    if self._conn:
      self._conn.settimeout(self.websocket_timeout)

  # * LOW LEVEL METHODS ----------------------------------
  def execute(self, query, variables=None):
    """This function executes the intructions of a query or mutation.

    Args:
        query (string): Graphql instructions.
        variables (string, optional): Variables of the transaction. Defaults
         to None.

    Raises:
        Exception: There is not setted a main environment.
        Exception: Transactions format error.

    Returns:
        [JSON]: Raw GraphqlResponse.
    """
    data = {
      'query': query,
      'variables': variables
    }
    env = self.environments.get(self.environment, None)
    if not env:
      raise Exception(f'cannot execute query without setting an environment')
    headers = {
      'Accept': 'application/json',
      'Content-Type': 'application/json'
      }
    env_headers = env.get('headers', None)
    post_timeout = env.get('post_timeout', '60')
    if env_headers:
      headers.update(env_headers)
    response = requests.post(env['url'], json=data, headers=headers, timeout=int(post_timeout))
    if response.status_code == 200:
      return response.json()
    else:
      raise Exception(
        "Query failed to run by returning code of {}.\n{}".format(
          response.status_code, query))
