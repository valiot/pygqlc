import pytest
from pygqlc import GraphQLClient # main package
from .pygqlc import queries # tests folder

@pytest.fixture
def gql():
  import os
  gql = GraphQLClient()
  gql.addEnvironment(
      'dev',
      url=os.environ.get('API'),
      wss=os.environ.get('WSS'),
      headers={'Authorization': os.environ.get('TOKEN')},
      default=True)
  return gql
