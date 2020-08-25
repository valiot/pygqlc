import pytest
from pygqlc import GraphQLClient # main package

class EnvironmentVariablesException(Exception):
  """Check your environment variables"""

class AuthorsModelException(Exception):
  """There is a problem with the author model."""

class RecordException(Exception):
  """Record doesn't exists in author model"""

def query_authors(name=""):
  name_filter = '{name:"'+ name +'"}'
  if not name:
    return "query {authors{id}}"
  authors_query = "query {authors(filter:?){id}}".replace('?', name_filter)
  return authors_query


@pytest.fixture(scope="session")
def gql():
  import os
  import sys

  try:
    if not os.environ.get('API'):
      raise EnvironmentError
    if not os.environ.get('WSS'):
      raise EnvironmentError
    if not os.environ.get('TOKEN'):
      raise EnvironmentError
  except EnvironmentError:
    sys.exit("Check your environment variables")

  gql = GraphQLClient()
  gql.addEnvironment(
    'dev',
    url=os.environ.get('API'),
    wss=os.environ.get('WSS'),
    headers={'Authorization': os.environ.get('TOKEN')},
    default=True)


  try:
    _, errors = gql.query(query_authors(), flatten=True)
    if not errors == []:
      raise AuthorsModelException
  except AuthorsModelException:
    sys.exit(errors)

  try:

    _, errors_pau = gql.query(query_authors("Paulinna"))
    _, errors_baruc = gql.query(query_authors("Baruc"))

    if any([errors_baruc, errors_pau]):
      raise RecordException
  except RecordException:
    sys.exit(errors_pau, errors_baruc)
  
  yield gql
  # ! Teardown for GQL fixture
  gql.close()
