"""
# ! mutation complex example:

mutation MutationAlias(
  $param1: Type1
  $param2: Type2
  $param3: Type3
  ...
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

# ! Mutation simple example:
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

>>> m = '''mutation{createAuthor(name: $name, enabled: $enabled){successful}}'''
>>> m.replace('$name', 'Baruc')
'mutation{createAuthor(name: Baruc, enabled: $enabled){successful}}'
>>> m.replace('$name', 'Baruc')
'mutation{createAuthor(name: Baruc, enabled: $enabled){successful}}'
>>> m.replace('$name', 10)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
TypeError: replace() argument 2 must be str, not int
>>> m.replace('$name', str(10))
'mutation{createAuthor(name: 10, enabled: $enabled){successful}}'
>>> import re
>>> text = m
>>> m_regex = 'mutation{(.+?)}'
>>> found = re.search(m_regex, text).group(1)
>>> found
'createAuthor(name: $name, enabled: $enabled){successful'
>>> m_regex = '^mutation{(.+?)}$'
>>> found = re.search(m_regex, text).group(1)
>>> found
'createAuthor(name: $name, enabled: $enabled){successful}'
>>> m = '''mutation{  createAuthor(name: $name, enabled: $enabled){successful}   }'''
>>> found = re.search(m_regex, text).group(1)
>>> found
'createAuthor(name: $name, enabled: $enabled){successful}'
>>> q1 = '''query{author(findBy:{name: $name}){id name}}'''
>>> q2 = '''{author(findBy:{name: $name}){id name}}'''
>>> q3 = '''query GetAuthor($name: String!){author(findBy:{name: $name}){id name}}'''
"""

class MutationBatch:
  def __init__(self, client):
    self.client = client

  def __enter__(self):
    print(f'setting things up with client {self.client}')
  
  def __exit__(self, type, value, traceback):
    print(f'tear down things in {self.client}')
  
