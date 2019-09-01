import requests
import json
from singleton_decorator import singleton
from tenacity import (
  retry, 
  retry_if_result, 
  stop_after_attempt, 
  wait_random
)

def has_errors(result):
  data, errors = result
  print(result)
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
    self.environments = {}
    self.environment = None
  
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
  def query(self, query, variables=None, flatten=True):
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
        data = data_flatten(data)
    except Exception as e:
      errors = [{'message': str(e)}]
    return data, errors

  # * Query high level implementation
  def query_one(self, query, variables=None, flatten=True):
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
        data = data_flatten(data, single_child=True)
    except Exception as e:
      errors = [{'message': str(e)}]
    return data, errors
  
  # TODO: Mutation high level implementation
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
  # TODO: Subscription high level implementation
  # * helper methods
  def addEnvironment(self, name, url=None, default=False):
    self.environments.update({
      name: {
        'url': url,
        'headers': {}
      }
    })
    if default:
      self.setEnvironment(name)
  def setUrl(self, environment=None, url=None):
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    self.environments.update(environment, {'url': url})
  
  def addHeader(self, environment=None, header={}):
    # if environment is not selected, use current environment
    if not environment:
      environment = self.environment
    headers = self.environments[environment].get('headers', None)
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
