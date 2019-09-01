from pygqlc import GraphQLClient
from tests.pygqlc import subscriptions as subs
from tests.pygqlc import mutations as muts
# gql = GraphQLClient()

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


# unsub_1 = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
# unsub_2 = gql.subscribe(subs.sub_author_created, callback=on_author_created)

# ! To trigger subscription:
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': True})
# data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': False})
# data, errors = gql.mutate(muts.create_author, {'name': 'Juanito', 'lastName': 'Saldi'})

# ! to exit:
# >> gql.close()
# >> exit()
