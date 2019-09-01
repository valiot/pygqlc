from .GraphQLClient import GraphQLClient 
def main():
  print('setup for GQL client')
  import os
  gql = GraphQLClient()
  gql.addEnvironment(
      'dev',
      url=os.environ.get('API'),
      wss=os.environ.get('WSS'),
      headers={'Authorization': os.environ.get('TOKEN')},
      default=True)

if __name__ == "__main__":
  main()
