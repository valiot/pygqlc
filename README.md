# pygqlc

Python client for graphql APIs

### Scope

This is an open source project, please feel free to fork it and PR to contribute with the community!
Repo for the project: https://github.com/valiot/pygqlc

### Features

- Fast and efficient GraphQL client
- Support for queries, mutations, and subscriptions
- Async capabilities for modern Python applications
- Connection pooling for better performance
- IPv4/IPv6 network flexibility
- Intelligent error handling and reporting
- Easy-to-use API with minimal boilerplate

### Installation

Requirements:

- Python 3.9+
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
    headers={'Authorization': f"Bearer {os.environ.get('TOKEN')}"},
    ipv4_only=False,  # Set to True to force IPv4 connections (useful for environments with problematic IPv6)
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

#### Exception Handling

You can directly import the `GQLResponseException` for better error handling:

```python
from pygqlc import GraphQLClient, GQLResponseException

gql = GraphQLClient()
# ... configure client ...

try:
    data, errors = gql.query('{ invalidQuery }')
    # Process data if no errors
except GQLResponseException as e:
    print(f"GraphQL error: {e.message}, Status: {e.status_code}")
    # Handle the exception appropriately
```

The subscribe method, returns an `unsubscribe` function,
this allows to stop subscriptions whenever needed.

After finishing all subscriptions, the method
`GraphQLClient.close()` should be called to close correctly the open GQL/websocket connections.

To reset all subscriptions and websocket connection use the method `GraphQLClient.resetSubsConnection()`.

To be noted:

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

### IPv4 Only Connections

In some network environments, particularly on Linux systems, IPv6 connectivity issues can cause slow requests. To force the client to use IPv4 connections only, you can set the `ipv4_only` parameter when adding an environment:

```python
gql.addEnvironment(
    'dev',
    url="https://api.example.com/graphql",
    ipv4_only=True  # Force IPv4 connections
)
```

This can resolve connectivity issues in networks with suboptimal IPv6 configurations.

### for mantainers:

#### Initial configuration

first of all, ensure you have configured poetry repositories correctly:
`poetry config repositories.valiot https://pypi.valiot.io/`

and their credentials:

For private valiot's pypi:

`poetry config http-basic.valiot <username> <password>`

(_ask adrian to send you the proper username and password for this step_)

And for public pypi:

`poetry config pypi-token.pypi <pypi-token>`

(_ask adrian or baruc to generate a token for you_)

then,

#### regular publish steps (after initial configuration)

deploy using:

`poetry version <patch | minor | major>`

then publish to valiot's private pypi:

`poetry publish --build -r valiot # build and PUBLISH TO PRIVATE VALIOTs PYPI`

or:

`poetry publish -r valiot`

(if you already built the package)

then publish to public pypi:

`poetry publish`

After release, publish to github:

`cat pygqlc/__version__.py`

`gh release create`

`gh release upload v<#.#.#> ./dist/pygqlc-<#.#.#>-py3-none-any.whl`

and don't forget to keep the `CHANGELOG.md` updated!

## Async Usage

Python 3.10+ supports async/await syntax for asynchronous programming. The GraphQLClient class provides async versions of the main methods:

```python
import asyncio
from pygqlc import GraphQLClient

async def main():
    client = GraphQLClient()
    client.addEnvironment('dev', "https://api.example.com/graphql")

    # Async query
    data, errors = await client.async_query('''
        query {
            users {
                id
                name
            }
        }
    ''')

    if not errors:
        print("Users:", data)

    # Async mutation
    data, errors = await client.async_mutate('''
        mutation {
            createUser(input: {name: "John Doe"}) {
                user {
                    id
                    name
                }
            }
        }
    ''')

    if not errors:
        print("Created user:", data)

if __name__ == "__main__":
    asyncio.run(main())
```

The async methods are:
- `async_execute`: Low-level method to execute GraphQL operations
- `async_query`: For GraphQL queries
- `async_query_one`: For queries that return a single item
- `async_mutate`: For GraphQL mutations

These methods can be used with `await` in async functions and provide the same functionality as their synchronous counterparts, but with the benefits of asynchronous execution.