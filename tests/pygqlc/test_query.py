import queries
def test_query_no_errors(gql):
  _, errors = gql.query(queries.get_authors)
  assert errors == []

def test_query_has_errors(gql):
  _, errors = gql.query(queries.bad_get_authors)
  assert len(errors) > 0