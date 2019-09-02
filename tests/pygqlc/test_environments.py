def test_enter_environ(gql):
  original_env = gql.environment
  with gql.enterEnvironment('test'):
    context_env = gql.environment
    assert context_env == 'test', \
      'environment should change inside WITH statement'
  assert gql.environment == original_env, \
    'environment should go back to original when outside of WITH statement'
