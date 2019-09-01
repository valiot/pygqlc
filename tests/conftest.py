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

# * Query fixtures:
@pytest.fixture
def q_authors(gql):
  return gql.query(queries.get_authors, flatten=True)

@pytest.fixture
def q_authors_not_flat(gql):
  return gql.query(queries.get_authors, flatten=False)

@pytest.fixture
def q_bad_authors(gql):
  return gql.query(queries.bad_get_authors)

@pytest.fixture
def q_auth_siblings(gql):
  return gql.query(queries.get_authors_siblings, {'lastName': 'Martinez'})

@pytest.fixture
def q_bad_auth_siblings(gql):
  # ! variables MUST be dict, not list or else
  return gql.query(queries.get_authors_siblings, [{'lastName': 'Martinez'}])

@pytest.fixture
def q_last_author(gql):
  return gql.query_one(queries.get_last_author)

@pytest.fixture
def q_authors_noname(gql):
  # ! Should always be None
  return gql.query_one(queries.get_authors_no_name)
