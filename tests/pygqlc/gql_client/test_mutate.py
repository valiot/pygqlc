import pydash as py_
from . import mutations

def test_mutate_no_errors(gql):
  _, errors = gql.mutate(mutations.author_activate)
  assert errors == [], \
    'There should NOT be errors on this mutation'

def test_mutate_var(gql):
  data_1, err_1 = gql.mutate(mutations.author_set_active, {'active': True})
  data_2, err_2 = gql.mutate(mutations.author_set_active, {'active': False})
  assert not any([len(err_1) > 0, len(err_2) > 0]), \
    'Mutation should NOT contain any errors'
  assert py_.get(data_1, 'result.active') == True, \
    'ACTIVE should be set to True'
  assert py_.get(data_2, 'result.active') == False, \
    'ACTIVE should be set to False'

def test_bad_mutate_doc(gql):
  _, errors = gql.mutate(mutations.bad_author_create)
  assert len(errors) > 0, \
    'Mutation SHOULD contain errors (bad syntax)'
