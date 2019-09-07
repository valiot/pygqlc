import re
# ! works, but quite slow when graphql query handles more than two items in the response (20+ seconds)
# query_regex = r'^\s*(query(\s+[a-zA-Z_]+[a-zA-Z_0-9]?)?)?\s*(\(\s*(((\$[a-zA-Z_]+[a-zA-Z_0-9]?)\s*:\s*([a-zA-Z_]+[a-zA-Z_0-9]?!?)\s*)+\s*)\))?\s*{\s*(\s*(([a-zA-Z_]+[a-zA-Z_0-9]?)\s*:)?\s*([a-zA-Z_]+[a-zA-Z_0-9]?\s*(\(\s*((.\s*)+)\s*\))?)\s*{\s*((.\s*)+)\s*})\s*}'

query_regex = r'^\s*(query(\s+[a-zA-Z_]+[a-zA-Z_0-9]?)?)?\s*(\(\s*(((\$[a-zA-Z_]+[a-zA-Z_0-9]?)\s*:\s*([a-zA-Z_]+[a-zA-Z_0-9]?!?)\s*)+\s*)\))?\s*{\s*((.\s*)+)\s*}\s*}'

class QueryParser:
  def __init__(self, gql_doc):
    self.gql_doc = gql_doc
    self.match = None
  
  def validate(self):
    self.match = re.match(query_regex, self.gql_doc)
    return self.match is not None
