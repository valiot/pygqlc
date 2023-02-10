# pygqlc
Python client for graphql APIs

### Scope
This is an open source project, please feel free to fork it and PR to contribute with the community!
Repo for the project: https://github.com/valiot/pygqlc

### Installation
Requirements:
- Python 3.6+
- Pipenv

Install directly from pypi:

```
$ cd <my-project-dir>
$ pipenv --python 3.7 # or 3.6
$ pipenv shell
$ pipenv install pygqlc
$ python
$ >> import pygqlc
$ >> print(pygqlc.name)
```
If you get "pygqlc" printed in the python repl, the installation succeded!

### Usage
```python
import os
from pygqlc import GraphQLClient 
gql = GraphQLClient()
gql.addEnvironment(
    'dev',
    url=os.environ.get('API'), # should be an https url
    wss=os.environ.get('WSS'), # should be an ws/wss url
    headers={'Authorization': os.environ.get('TOKEN')},
    default=True)
```
#### From now on, you can access to the main API:
`gql.query, gql.mutate, gql.subscribe`

For queries:
```python
query = '''
query{
  authors{
    name
  }
}
'''
data, errors = gql.query( query )
```

For mutations:
```python
create_author = '''
mutation {
  createAuthor(){
    successful
    messages{field message}
    result{id insertedAt}
  }
}
'''
data, errors = gql.mutate( create_author )
```

For subscriptions:

```python
def on_auth_created(message):
  print(message)

sub_author_created = '''
subscription{
  authorCreated{
    successful
    messages{field message}
    result{id insertedAt}
  }
}
'''
# unsub may be None if subscription fails (no internet connection, host unreachable, bad subscription doc, etc)
unsub = gql.subscribe(sub_author_created, callback=on_auth_created)
...
# when finishing the subscription:
unsub()
# when finishing all subscriptions:
gql.close()
```

The subscribe method, returns an `unsubscribe` function,
this allows to stop subscriptions whenever needed.

After finishing all subscriptions, the method
`GraphQLClient.close()` should be called to close correctly the open GQL/websocket connections.

To reset all subscriptions and websocket connection use the method `GraphQLClient.resetSubsConnection()`.

### To be noted:
All main methods from the API accept a `variables` param.
it is a dictionary type and may include variables from your queries or mutations:

```python
query_with_vars = '''
query CommentsFromAuthor(
  $authorName: String!
  $limit: Int
){
  author(
    findBy:{ name: $authorName }
  ){
    id
    name
    comments(
      orderBy:{desc: ID}
      limit: $limit
    ){
      id
      blogPost{name}
      body
    }
  }
}
'''

data, errors = gql.query(
  query=query_with_vars,
  variables={
    "authorName": "Baruc",
    "limit": 10
  }
)
```

There is also an optional parameter `flatten` that simplifies the response format:
```python
# From this:
response = {
  'data': {
    'authors': [
      { 'name': 'Baruc' },
      { 'name': 'Juan' },
      { 'name': 'Gerardo' }
    ]
  }
}
# To this:
authors = [
  { 'name': 'Baruc' },
  { 'name': 'Juan' },
  { 'name': 'Gerardo' }
]
```
Simplifying the data access from this:

`response['data']['authors'][0]['name']`

to this:

`authors[0]['name']`

It is `query(query, variables, flatten=True)` by default, to avoid writing it down everytime

The `(_, errors)` part of the response, is the combination of GraphQL errors, and communication errors, simplifying validations, it has this form:
```python
errors = [
  {"field": <value>, "message":<msg>},
  {"field": <value>, "message":<msg>},
  {"field": <value>, "message":<msg>},
  ...
]
```
The field Attribute it's only available for GraphQL errors, when it is included in the response, so it's suggested that every mutation has at least this parameters in the response:
```
mutation{
  myMutation(<mutationParams>){
    successful
    messages{
      field
      message
    }
    result{
      <data of interest>
    }
  }
}
```
### Post timeout:
You can set a post timeout to avoid an inactive process. 

Use `gql.setPostTimeout(seconds)`, or directly in the environment `gql.addEnvironment(post_timeout=seconds)`. Default port_timeout is 60 seconds

### Websocket timeout:
You can set a websocket timeout to keep subscriptions alive. 

Use `gql.setTimeoutWebsocket(seconds)`, or directly in the environment `gql.addEnvironment(timeoutWebsocket=seconds)`. Default timeoutWebsocket is 60 seconds

### for mantainers:
deploy using:
`python setup.py sdist bdist_wheel && python -m twine upload dist/* --skip-existing # UPLOAD TO PYPI`
