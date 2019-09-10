import re

mutation_regex = r'^\s*mutation\s*(\s+[a-zA-Z_]+[a-zA-Z_0-9]?)?\s*(\(\s*(((\$[a-zA-Z_]+[a-zA-Z_0-9]?)\s*:\s*([a-zA-Z_]+[a-zA-Z_0-9]?!?)\s*)+\s*)\))?\s*{\s*((.\s*)+\s*})\s*}'
rgx_groups = {
  'full_doc': 0,
  'alias': 1,
  'variables': 3,
  'content': 7,
}
class MutationParser:
  def __init__(self, gql_doc):
    self.re = re
    self.regex = mutation_regex
    self.gql_doc = gql_doc
    self.match = None
    self.isValid = False
    self.full_doc = None
    self.alias = None
    self.variables = None
    self.content = None

  def parse(self):
    # ! First, remove variable definitions:
    doc = self.gql_doc
    var_end = doc.find('{')
    short_doc = doc[var_end:]
    self.gql_doc = f'mutation {short_doc}'
    if self.validate():
      self.full_doc = self.match.group(rgx_groups['full_doc'])
      self.alias = self.match.group(rgx_groups['alias'])
      self.variables = self.match.group(rgx_groups['variables'])
      self.content = self.match.group(rgx_groups['content'])
      return True
    return False

  def validate(self):
    match = self.re.match(self.regex, self.gql_doc)
    self.isValid = match is not None
    if self.isValid:
      self.match = match
    return self.isValid
  
  def format_value(self, value):
    if type(value) == str:
      return f'"{value}"'
    elif type(value) == bool:
      return f'{"true" if value else "false"}'
    elif type(value) == type(None):
      return 'null'
    else:
      return str(value)
