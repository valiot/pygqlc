# >>> m = '''mutation{createAuthor(name: $name, enabled: $enabled){successful}}'''
# >>> m.replace('$name', 'Baruc')
# 'mutation{createAuthor(name: Baruc, enabled: $enabled){successful}}'
# >>> m.replace('$name', 'Baruc')
# 'mutation{createAuthor(name: Baruc, enabled: $enabled){successful}}'
# >>> m.replace('$name', 10)
# Traceback (most recent call last):
#   File "<stdin>", line 1, in <module>
# TypeError: replace() argument 2 must be str, not int
# >>> m.replace('$name', str(10))
# 'mutation{createAuthor(name: 10, enabled: $enabled){successful}}'
# >>> import re
# >>> text = m
# >>> m_regex = 'mutation{(.+?)}'
# >>> found = re.search(m_regex, text).group(1)
# >>> found
# 'createAuthor(name: $name, enabled: $enabled){successful'
# >>> m_regex = '^mutation{(.+?)}$'
# >>> found = re.search(m_regex, text).group(1)
# >>> found
# 'createAuthor(name: $name, enabled: $enabled){successful}'
# >>> m = '''mutation{  createAuthor(name: $name, enabled: $enabled){successful}   }'''
# >>> found = re.search(m_regex, text).group(1)
# >>> found
# 'createAuthor(name: $name, enabled: $enabled){successful}'
# >>> q1 = '''query{author(findBy:{name: $name}){id name}}'''
# >>> q2 = '''{author(findBy:{name: $name}){id name}}'''
# >>> q3 = '''query GetAuthor($name: String!){author(findBy:{name: $name}){id name}}'''

from .MutationParser import MutationParser
from pprint import pprint

"""The purpuse of this module is batch and execute a graphql transaction, such
 as a query or mutation.
"""
class InvalidMutationException(Exception):
  """This class is to define the InvalidMutationException
  """
  pass

class MutationBatch:
  """This is the mutation batch class, it can generate and execute a batch of 
  graphql's transaction.

  Args:
      client (GraphQLClient Object, optional): Instance of the GraphQLClient.
        Defaults to None.
      label (str, optional): Label that will get each transaction of the batch.
        Defaults to 'mutation'.

  Examples:
      >>> Batch example:
        with gql.batchMutate(label='mut') as batch:
          for author in authors:
            batch.add(
              muts.create_author, {
                'name': author['name']
              }
            )
          data, errors = batch.execute()
          print(data)

      >>> Mutation simple example: 
        mutation {
          label_1: mutationName(
            param1: valx
            param2: valy
          ){
            response1
          }
          label_2: mutationName2(
            param1: valz
          ){
            response2
          }
        }

      >>> Mutation complex example: 
        mutation MutationAlias(
          >>>$param1: Type1
          $param2: Type2
          $param3: Type3
          ){
          label_1: mutationName(
            param1: $param1
            param2: $param2
          ){
            response1
          }
          label_2: mutationName2(
            param1: $param3
          ){
            response2
          }
        }
  
  """
  def __init__(self, client=None, label='mutation'):
    """Constructor of the MutatuibBatch object.
    """
    self.client = client
    self.start_tag = 'mutation BatchMutation {'
    self.batch_doc = ''
    self.close_tag = '}'
    self.label = label
    self.count = 1

  def __enter__(self):
    # print(f'setting things up with client {self.client}')
    return self
  
  def __exit__(self, type, value, traceback):
    pass # print(f'tear down things in {self.client}')
  
  def append(self, doc, variables={}):
    """This function makes each transactions for the batch.

    Args:
        doc (string): GraphQL transaction intructions.
        variables (dict, optional): Variables of the transaction. Defaults to {}.

    Raises:
        InvalidMutationException: It raises when the doc is invalid.
    """
    # extract document tokens
    mp = MutationParser(doc)
    valid_doc = mp.parse()
    if not valid_doc:
      raise InvalidMutationException('Invalid mutation document')
    # build batch mutation from extracted tokens
    parsed_doc = mp.content
    for key, value in variables.items():
      parsed_doc = parsed_doc.replace(f'${key}', mp.format_value(value))
    self.batch_doc += f'\t{self.label}_{self.count}: {parsed_doc}\n'
    self.count += 1
  
  def get_doc(self):
    """This function builds the transaction.

    Returns:
        (string): Returns the full transaction, ready to execute.
    """
    full_doc = f'''{self.start_tag}\n{self.batch_doc} {self.close_tag}'''
    return full_doc

  def execute(self):
    """This function can execute a TransactionBatch.

    Returns:
        (GraphqlResponse): Returns the Graphql response.
    """
    error_dict = {}
    data, errors = self.client.mutate(self.get_doc())
    if errors:
      error_dict['server'] = errors
    if data:
      for label, response in data.items():
        error_dict[label] = response.get('messages', [])
    return data, error_dict
