import pytest
from pygqlc import GraphQLClient # main package
from .pygqlc import queries # tests folder

@pytest.fixture(scope="module")
def gql(request):
  import os
  gql = GraphQLClient()
  gql.addEnvironment(
    'dev',
    url=os.environ.get('API'),
    wss=os.environ.get('WSS'),
    headers={'Authorization': os.environ.get('TOKEN')},
    default=True)
  def finish():
    '''Teardown function for GQL fixture'''
    gql.close()
  request.addfinalizer(finish)
  return gql
