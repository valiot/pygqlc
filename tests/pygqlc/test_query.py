import pydash as _py
import queries

def test_query_no_errors(q_authors):
  _, errors = q_authors
  assert errors == [], \
    'query must NOT contain errors'

def test_query_has_errors(q_bad_authors):
  _, errors = q_bad_authors
  assert len(errors) > 0, \
    'query MUST contain errors'


def test_query_flatten(q_authors):
  data, _ = q_authors # ! flatten=True by default
  assert not _py.get(data, 'data'), \
    'data must NOT appear as response root'


def test_query_not_flatten(q_authors_not_flat):
  data, _ = q_authors_not_flat
  assert _py.get(data, 'data'),  \
    'data must appear as response root'


def test_query_vars(q_auth_siblings):
  _, errors = q_auth_siblings
  assert errors == [], \
      'query must NOT contain errors'


def test_query_bad_vars(q_bad_auth_siblings):
  _, errors = q_bad_auth_siblings
  assert len(errors) > 0, \
      'query MUST contain errors'
