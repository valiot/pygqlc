import pydash as _py
from . import queries

def test_query_no_errors(gql):
  _, errors = gql.query(queries.get_authors, flatten=True)
  assert errors == [], \
    'query must NOT contain errors'

def test_query_has_errors(gql):
  _, errors = gql.query(queries.bad_get_authors)
  assert len(errors) > 0, \
    'query MUST contain errors'


def test_query_flatten(gql):
  data, _ = gql.query(queries.get_authors, flatten=True) # ! flatten=True by default
  assert not _py.get(data, 'data'), \
    'data must NOT appear as response root'


def test_query_not_flatten(gql):
  data, _ = gql.query(queries.get_authors, flatten=False)
  assert _py.get(data, 'data'),  \
    'data must appear as response root'


def test_query_vars(gql):
  _, errors = gql.query(
    queries.get_authors_siblings, 
    {'lastName': 'Martinez'}
  )
  assert errors == [], \
      'query must NOT contain errors'


def test_query_bad_vars(gql):
  _, errors = gql.query(
    queries.get_authors_siblings,
    [{'lastName': 'Martinez'}]
  )
  assert len(errors) > 0, \
      'query MUST contain errors'
