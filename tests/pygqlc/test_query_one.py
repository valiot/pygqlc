def test_query_one_flatten(q_last_author):
  data, _ = q_last_author
  print(data)
  assert type(data) == dict, \
    'Query result must be of type dict'
  assert all(key in data.keys() for key in ['name', 'lastName']), \
    'Query must contain name and lastName data'


def test_query_one_null(q_authors_noname):
  data, _ = q_authors_noname
  print(data)
  assert data is None, \
    'query_one must return None if empty list'
