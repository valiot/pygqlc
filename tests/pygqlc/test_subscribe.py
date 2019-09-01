from pygqlc import GraphQLClient
from tests.pygqlc import subscriptions as subs
from tests.pygqlc import mutations as muts
gql = GraphQLClient()
def on_author_updated(_id, msg):
  if(msg['successful']):
    author = msg['result']
    print(f'author {author["name"]} was updated successfully')
  else:
    print(f'error creating author: {msg["messages"]}')

def on_author_created(_id, msg):
  if(msg['successful']):
    author = msg['result']
    print(f'author {author["name"]} was created successfully')
  else:
    print(f'error creating author: {msg["messages"]}')

unsub_1 = gql.subscribe(subs.sub_author_updated, callback=on_author_updated)
unsub_2 = gql.subscribe(subs.sub_author_created, callback=on_author_created)
data, errors = gql.mutate(muts.update_any_author_active, {'name': 'Baruc', 'active': True})
data, errors = gql.mutate(muts.create_author, {'name': 'Juanito', 'lastName': 'Saldi'})
wss_msg = {
  'type': 'data',
  'id': 0,
  'payload': {
    'data': {
      'authorUpdated': {
        'successful': True, 
        'messages': [], 
        'result': {
          'id': '7', 
          'name': 'Baruc', 
          'lastName': 'Almaguer', 
          'active': True, 
          'dateOfBirth': None, 
          'updatedAt': '2019-09-01T18:05:55Z'
        }
      }
    }
  }
}
