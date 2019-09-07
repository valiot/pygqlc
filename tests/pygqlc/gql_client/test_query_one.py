from . import queries
def test_query_one_flatten(gql):
  data, _ = gql.query_one(queries.get_last_author)
  assert type(data) == dict, \
    'Query result must be of type dict'
  assert all(key in data.keys() for key in ['name', 'lastName']), \
    'Query must contain name and lastName data'


def test_query_one_null(gql):
  data, _ = gql.query_one(queries.get_authors_no_name)
  assert data is None, \
    'query_one must return None if empty list'
