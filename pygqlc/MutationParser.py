import re

"""
The purpose of this module is to prepare a graphql transaction, such as a query
 or mutation, to be able to carry out a batch of them.
"""

mutation_regex = r'^\s*mutation\s*(\s+[a-zA-Z_]+[a-zA-Z_0-9]?)?\s*(\(\s*(((\$[a-zA-Z_]+[a-zA-Z_0-9]?)\s*:\s*([a-zA-Z_]+[a-zA-Z_0-9]?!?)\s*)+\s*)\))?\s*{\s*((.\s*)+\s*})\s*}'
rgx_groups = {
  'full_doc': 0,
  'alias': 1,
  'variables': 3,
  'content': 7,
}
class MutationParser:
  """This is the MutationParser class, it can parse a graphql instructions.
  """
  def __init__(self, gql_doc):
    """Constructor of the MutationParser object.

    Args:
        gql_doc (string): Graphql instructions

    Attributes:
        re (module): Regexp module.
        regex (regex): Transaction Regex.
        match (Match Object): Match object of the pattern and doc. Defaults to
          None.
        isValid (boolean): Checks if the gql_doc is valid. Defaults to False.
        full_doc (string): All Graphql instructions.
        alias (string): Name of the transaction.
        variables (string): Variables of the transaction.
        content (content): The transaction content.
    """
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
    """This fuction parses and validates the transaction instructions.3

    Returns:
        (boolean): Returns if the parsed doc was succesful.
    """
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
    """This function checks if the transaction instructions has match with the
     transaction regex.

    Returns:
        (boolean): Returns if it is valid or not.
    """
    match = self.re.match(self.regex, self.gql_doc)
    self.isValid = match is not None
    if self.isValid:
      self.match = match
    return self.isValid
  
  def format_value(self, value):
    """This function formats document's values.

    Args:
        value (any): Value that want to format.

    Returns:
        (string): Returns a formated string.
    """
    if type(value) == str:
      return f'"{value}"'
    elif type(value) == bool:
      return f'{"true" if value else "false"}'
    elif type(value) == type(None):
      return 'null'
    else:
      return str(value)
