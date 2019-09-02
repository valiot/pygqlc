import subscriptions as subs
import mutations as muts
import types

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
  sub_id = gql.sub_counter + 1
  unsub_1 = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
  assert type(unsub_1) == types.FunctionType, \
    'subscribe should return an unsubscribe function'
  assert len(gql.subs.items()) > 0, \
    'There should be at least ONE subscription active'
  assert gql.subs.get(sub_id) is not None, \
    'The subscription did not start with the correct ID'

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

