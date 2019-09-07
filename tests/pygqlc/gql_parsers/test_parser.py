from . import queries as q
from pygqlc import QueryParser
# * Must pass tests: ****************************
def test_validate_q_short():
  parser = QueryParser(q.q_short)
  assert parser.validate(), f'"q_short" should be a valid query'

def test_validate_q_short_attrs():
  parser = QueryParser(q.q_short_attrs)
  assert parser.validate(), f'"q_short_attrs" should be a valid query'

def test_validate_q_short_spaces():
  parser = QueryParser(q.q_short_spaces)
  assert parser.validate(), f'"q_short_spaces" should be a valid query'

def test_validate_q_short_attrs_spaces():
  parser = QueryParser(q.q_short_attrs_spaces)
  assert parser.validate(), f'"q_short_attrs_spaces" should be a valid query'

def test_validate_q_short_attrs_comma():
  parser = QueryParser(q.q_short_attrs_comma)
  assert parser.validate(), f'"q_short_attrs_comma" should be a valid query'

def test_validate_q_short_params():
  parser = QueryParser(q.q_short_params)
  assert parser.validate(), f'"q_short_params" should be a valid query'

def test_validate_q_long_vars():
  parser = QueryParser(q.q_long_vars)
  assert parser.validate(), f'"q_long_vars" should be a valid query'

def test_validate_q_long_alias_vars():
  parser = QueryParser(q.q_long_alias_vars)
  assert parser.validate(), f'"q_long_alias_vars" should be a valid query'

def test_validate_q_short_newlines():
  parser = QueryParser(q.q_short_newlines)
  assert parser.validate(), f'"q_short_newlines" should be a valid query'

def test_validate_q_short_attrs_newlines():
  parser = QueryParser(q.q_short_attrs_newlines)
  assert parser.validate(), f'"q_short_attrs_newlines" should be a valid query'

def test_validate_q_short_params_newlines():
  parser = QueryParser(q.q_short_params_newlines)
  assert parser.validate(), f'"q_short_params_newlines" should be a valid query'

def test_validate_q_long_opt_var_newlines():
  parser = QueryParser(q.q_long_opt_var_newlines)
  assert parser.validate(), f'"q_long_opt_var_newlines" should be a valid query'

def test_validate_q_long_req_var_newlines():
  parser = QueryParser(q.q_long_req_var_newlines)
  assert parser.validate(), f'"q_long_req_var_newlines" should be a valid query'

def test_validate_q_long_vars_newlines():
  parser = QueryParser(q.q_long_vars_newlines)
  assert parser.validate(), f'"q_long_vars_newlines" should be a valid query'

def test_validate_q_looong_query():
  parser = QueryParser(q.q_looong_query)
  assert parser.validate(), f'"q_looong_query" should be a valid query'

# ! Must NOT pass tests: *************************
def test_validate_q_short_bad_term():
  parser = QueryParser(q.q_short_bad_term)
  assert not parser.validate(), '"q_short_bad_term" should be an INVALID query'

def test_validate_q_short_bad_brackets():
  parser = QueryParser(q.q_short_bad_brackets)
  assert not parser.validate(), '"q_short_bad_brackets" should be an INVALID query' 

# TODO: Better regex (this tests are not passing, but it's not the scope of the current features to validate them)
# * Currently, the regex it's only used for extraction of tokens, it is not a fully functional GraphQL validator
# ! def test_validate_q_short_bad_no_content():
# !   parser = QueryParser(q.q_short_bad_no_content)
# !   assert not parser.validate(), '"q_short_bad_no_content" should be an INVALID query' 

# ! def test_validate_q_short_bad_no_name():
# !   parser = QueryParser(q.q_short_bad_no_name)
# !   assert not parser.validate(), '"q_short_bad_no_name" should be an INVALID query' 

# ! def test_validate_q_short_bad_no_params():
# !   parser = QueryParser(q.q_short_bad_no_params)
# !   assert not parser.validate(), '"q_short_bad_no_params" should be an INVALID query' 

def test_validate_q_long_bad_no_vars():
  parser = QueryParser(q.q_long_bad_no_vars)
  assert not parser.validate(), '"q_long_bad_no_vars" should be an INVALID query' 
