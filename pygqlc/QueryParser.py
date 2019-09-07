import re
query_regex = r'^(query\s*\(\s*.+\s*\))?\s*{\s*(.+)\s*}'

class QueryParser:
  def __init__(self, gql_doc):
    self.gql_doc = gql_doc
    self.match = None
  
  def validate(self):
    self.match = re.match(query_regex, self.gql_doc)
    return self.match is not None
