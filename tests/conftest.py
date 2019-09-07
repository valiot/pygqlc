import pytest
from pygqlc import GraphQLClient # main package

@pytest.fixture(scope="session")
def gql():
  import os
  gql = GraphQLClient()
  gql.addEnvironment(
    'dev',
    url=os.environ.get('API'),
    wss=os.environ.get('WSS'),
    headers={'Authorization': os.environ.get('TOKEN')},
    default=True)
  yield gql
  # ! Teardown for GQL fixture
  gql.close()
