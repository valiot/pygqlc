import requests
import json
import time
import threading
import websocket
from singleton_decorator import singleton
from tenacity import (
  retry, 
  retry_if_result, 
  stop_after_attempt, 
  wait_random
)

GQL_WS_SUBPROTOCOL = "graphql-ws"

def has_errors(result):
  _, errors = result
  return len(errors) > 0

def data_flatten(data, single_child=False):
  if type(data) == dict:
    keys = list(data.keys())
    if len(keys) == 1:
      key = list(data.keys())[0]
      return data_flatten(data[key], single_child)
    else:
      return data # ! various elements, nothing to flatten
  elif single_child and type(data) == list:
    if len(data) == 1:
      return data_flatten(data[0], single_child)
    elif len(data) == 0:
      return None # * Return none if no child was found
    else:
      return data
  else:
    return data # ! not a dict, nothing to flatten

# ! Example With:
'''
client = GraphQLClient()
with client.enterEnvironment('dev') as gql:
    data, errors = gql.query('{lines(limit:2){id}}')
    print(data, errors)
'''

# ! Example setEnvironment:
'''
client = GraphQLClient()
client.addEnvironment('dev', "https://heineken.valiot.app/")
client.addHeader(
    environment='dev', 
    header={'Authorization': dev_token})
data, errors = gql.query('{lines(limit:2){id}}')
print(data, errors)
'''

@singleton
class GraphQLClient:
  def __init__(self):
    # * query/mutation related attributes
    self.environments = {}
    self.environment = None
    # * wss/subscription related attributes:
    self.ws_url = None
    self._conn = None
    self._subscription_running = False
    self._st_id = None
  
  # * with <Object> implementation
  def __enter__(self):
    return self
  
  def __exit__(self, type, value, traceback):
    self.environment = self.save_env # restores environment
    return
  
  def enterEnvironment(self, name):
    self.save_env = self.environment
    self.environment = name
    return self # * for use with "with" keyword
  
  # * HIGH LEVEL METHODS ---------------------------------
  # TODO: Implement tenacity in query, mutation and subscription methods
  @retry(
    retry=(retry_if_result(has_errors)),
    stop=stop_after_attempt(5),
    wait=wait_random(min=0.25, max=0.5))
  def query_wrapper(self, query, variables=None):
    data = None
    errors = []
    try:
      result = self.execute(query, variables)
      data = result.get('data', None)
      errors = result.get('errors', [])
    except Exception as e:
      errors = [{'message': str(e)}]
    return data, errors
  
  # * Query high level implementation
  def query(self, query, variables=None, flatten=True, single_child=False):
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
    return self.query(query, variables, flatten=True, single_child=True)
  
  # * Mutation high level implementation
  def mutate(self, mutation, variables=None, flatten=True):
    response = {}
    data = None
    errors = []
    try:
      response = self.execute(mutation, variables)
    except Exception as e:
      errors = [{'message': str(e)}]
    finally:
      errors = response.get('errors', [])
      if(not errors):
        data = response.get('data', None)
      if flatten:
        data = data_flatten(data)
        if (data):
          errors.extend(data.get('messages', []))
    return data, errors
  # * Subscription high level implementation ******************
  def subscribe(self, query, variables=None, callback=None):
    # initialize websocket only once
    if not self._conn:
      env = self.environments.get(self.environment, None)
      self.ws_url = env.get('wss')
      self._conn = websocket.create_connection(
        self.ws_url,
        on_message=self._on_message,
        subprotocols=[GQL_WS_SUBPROTOCOL])
      self._conn.on_message = self._on_message
    self._conn_init()
    payload = {'query': query, 'variables': variables}
    _cc = self._on_message if not callback else callback
    _id = self._start(payload)
    def subs(_cc):
      self._subscription_running = True
      while self._subscription_running:
        r = json.loads(self._conn.recv())
        if r['type'] == 'error' or r['type'] == 'complete':
          print(r)
          self.stop_subscribe(_id)
          break
        elif r['type'] != 'ka':
          _cc(_id, r)
        time.sleep(1)
    self._st_id = threading.Thread(target=subs, args=(_cc,))
    self._st_id.start()


  def stop_subscribe(self, _id):
    self._subscription_running = False
    self._st_id.join()
    self._stop(_id)

  def close(self):
    self._conn.close()
  
  def _on_message(self, message):
    data = json.loads(message)
    # skip keepalive messages
    if data['type'] != 'ka':
      print(message)
  
  def _conn_init(self):
    env = self.environments.get(self.environment, None)
    headers = env.get('headers', {})
    payload = {
      'type': 'connection_init',
      'payload': headers
    }
    self._conn.send(json.dumps(payload))
    self._conn.recv()

  def _start(self, payload):
    _id = '1' # gen_id() # ! Probably requires auto-increment, more than random ID generation
    frame = {'id': _id, 'type': 'start', 'payload': payload}
    self._conn.send(json.dumps(frame))
    return _id

  def _stop(self, _id):
    payload = {'id': _id, 'type': 'stop'}
    self._conn.send(json.dumps(payload))
    return self._conn.recv()
  
  # * END SUBSCRIPTION functions ******************************
  # * helper methods
  def addEnvironment(self, name, url=None, wss=None, headers={}, default=False):
    self.environments.update({
      name: {
        'url': url,
        'wss': wss,
        'headers': headers
      }
    })
    if default:
      self.setEnvironment(name)
  def setUrl(self, environment=None, url=None):
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments.update(environment, {'url': url})
  
  def setWss(self, environment=None, url=None):
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments.update(environment, {'wss': url})
  
  def addHeader(self, environment=None, header={}):
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    headers = self.environments[environment].get('headers', {})
    headers.update(header)
    self.environments[environment]['headers'].update(headers)

  def setEnvironment(self, name):
    env = self.environments.get(name, None)
    if not env:
      raise Exception(f'selected environment not set ({name})')
    self.environment = name

  # * LOW LEVEL METHODS ----------------------------------
  def execute(self, query, variables=None):
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
    if env_headers:
      headers.update(env_headers)
    response = requests.post(env['url'], json=data, headers=headers)
    if response.status_code == 200:
      return response.json()
    else:
      raise Exception(
        "Query failed to run by returning code of {}.\n{}".format(
          response.status_code, query))
