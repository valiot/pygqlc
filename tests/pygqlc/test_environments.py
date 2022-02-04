import pytest

def test_enter_environ(gql):
  original_env = gql.environment
  with gql.enterEnvironment('test'):
    context_env = gql.environment
    assert context_env == 'test', \
      'environment should change inside WITH statement'
  assert gql.environment == original_env, \
    'environment should go back to original when outside of WITH statement'

def test_change_url_environment(gql):
  import os
  test_url = 'https://some.url.io'
  env = gql.environment
  url = gql.environments[env]['url']
  gql.setUrl(url=test_url)
  new_url = gql.environments[env]['url']
  gql.setUrl(url=url) # return URL to default
  assert new_url == test_url, \
    'URL should set on current environment as default'


def test_change_wss_environment(gql):
  import os
  test_url = 'wss://some.websocket.io'
  env = gql.environment
  url = gql.environments[env]['wss']
  gql.setWss(url=test_url)
  new_url = gql.environments[env]['wss']
  gql.setWss(url=url)  # return URL to default
  assert new_url == test_url, \
    'WSS URL should set on current environment as default'

def test_add_header_environment(gql):
  import os
  env = gql.environment
  original_headers = gql.environments[env]['headers']
  test_header = {'test_header': 'Bearer lasknsmthinsmthinflaks'}
  gql.addHeader(header=test_header)
  # ! verify header is included in new headers
  headers = gql.environments[env]['headers']
  assert headers.get('test_header') is not None, \
    '"test_header" should have been added to the GQL environment'
  # * teardown test (we don't want dummy headers in the test requests)
  gql.environments[env]['headers'] = original_headers

def test_change_post_timeout(gql):
  import os
  test_post_timeout = 103
  env = gql.environment
  post_timeout = gql.environments[env]['post_timeout']
  gql.setPostTimeout(post_timeout=test_post_timeout)
  new_post_timeout = gql.environments[env]['post_timeout']
  gql.setPostTimeout(post_timeout=post_timeout)  # return Timeout to default
  assert (new_post_timeout == test_post_timeout) and (post_timeout != new_post_timeout), \
    'Post timeout should set on current environment as default'

def test_set_bad_environment(gql):
  with pytest.raises(Exception):
    assert gql.setEnvironment('bad_environ'), \
      'Environment should not be set with an unregistered environment name'

def test_bad_environ_bad_query(gql):
  good_env = gql.environment
  gql.environment = 'bad_environ'  # ! force bad environment
  with pytest.raises(Exception):
    assert gql.execute('bad_environ'), \
        'Environment should not be set with an unregistered environment name'
  gql.setEnvironment(good_env)
