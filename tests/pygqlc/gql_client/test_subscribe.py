from . import subscriptions as subs
from . import mutations as muts
import types
import time

def on_author_updated(msg):
  if(msg['successful']):
    author = msg['result']
    print(f'author {author["name"]} was updated successfully')
  else:
    print(f'error creating author: {msg["messages"]}')

def on_author_created(msg):
  if(msg['successful']):
    author = msg['result']
    print(f'author {author["name"]} was created successfully')
  else:
    print(f'error creating author: {msg["messages"]}')

def test_subscribe_success(gql):
  sub_id = str(gql.sub_counter + 1)
  unsub_1 = gql.subscribe(subs.sub_author_created, callback=on_author_created)
  assert type(unsub_1) == types.FunctionType, \
    'subscribe should return an unsubscribe function'
  assert len(gql.subs.items()) > 0, \
    'There should be at least ONE subscription active'
  assert gql.subs.get(sub_id) is not None, \
    'The subscription did not start with the correct ID'

def test_sub_routing_loop_message(gql):
  sub_id = str(gql.sub_counter + 1)
  _ = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
  runs = gql.subs[sub_id]['runs']
  # * This should activate the subscription at least once:
  _ = gql.mutate(muts.update_any_author_active, {'name': 'Elon', 'lastname': 'Musk', 'active': True})
  _ = gql.mutate(muts.update_any_author_active, {'name': 'Elon', 'lastname': 'Musk', 'active': False})
  # ! We don't know how long will it take for the server to respond to the subscription:
  sub_triggered = False
  elapsed = 0
  timeout = 5.0 # * Max seconds to wait
  startTime = time.time()
  while not sub_triggered and elapsed < timeout:
    new_runs = gql.subs[sub_id]['runs']
    sub_triggered = new_runs > runs
    time.sleep(0.01) # * Give time to de server to react to the request
    elapsed = time.time() - startTime
  assert sub_triggered, \
    'Subscription should be triggered at least once'

def test_sub_default_callback(gql):
  sub_id = str(gql.sub_counter + 1)
  # * This adds coverage into the default callback
  _ = gql.subscribe(subs.sub_author_updated)
  runs = gql.subs[sub_id]['runs']
  # * This should activate the subscription at least once:
  _ = gql.mutate(muts.update_any_author_active, {'name': 'Elon', 'lastname': 'Musk', 'active': True})
  _ = gql.mutate(muts.update_any_author_active, {'name': 'Elon', 'lastname': 'Musk', 'active': False})
  # ! We don't know how long will it take for the server to respond to the subscription:
  sub_triggered = False
  elapsed = 0
  timeout = 5.0  # * Max seconds to wait
  startTime = time.time()
  while not sub_triggered and elapsed < timeout:
    new_runs = gql.subs[sub_id]['runs']
    sub_triggered = new_runs > runs
    time.sleep(0.01)  # * Give time to de server to react to the request
    elapsed = time.time() - startTime
  assert new_runs > runs, \
      'Subscription should be triggered at least once with default callback'
# from pygqlc import GraphQLClient
# from tests.pygqlc import subscriptions as subs
# from tests.pygqlc import mutations as muts
# gql = GraphQLClient()

# unsub_1 = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
# unsub_2 = gql.subscribe(subs.sub_author_created, callback=on_author_created)

# ! To trigger subscription:
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': True})
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': False})
# data, errors = gql.mutate(muts.create_author, {'name': 'Juanito', 'lastName': 'Saldi'})

# ! to exit:
# >> gql.close()
# >> exit()

