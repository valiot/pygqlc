
# * Valid short query
q_short = '{authors{id}}'
q_short_attrs = '{authors{id name lastName}}'
q_short_spaces = '{ authors { id } }'
q_short_attrs_spaces = '{ authors { id name lastName } }'
q_short_attrs_comma = '{ authors { id, name, lastName } }'
q_short_params = '{ authors( filter:{name:"Baruc"} ){ id } }'
q_long_vars = 'query ($name: String!){ authors(filter:{name:$name}){ id } }'
q_long_alias_vars = 'query BarucAuthors($name: String!){ authors(filter:{name:$name}){ id } }'
q_short_newlines = '''
  {
    authors {
      id
    }
  }
'''
q_short_attrs_newlines = '''
  {
    authors {
      id
      name
      lastName
    }
  }
'''
q_short_params_newlines = '''
  {
    authors (
      filter: {name: "Baruc"}
    ) {
      id
      name
    }
  }
'''
q_long_opt_var_newlines = '''
  query (
    $name: String
  ){
    authors (
      filter: {name: "Baruc"}
    ) {
      id
      name
    }
  }
'''
q_long_req_var_newlines = '''
  query (
    $name: String!
  ){
    authors (
      filter: { name: $name }
    ) {
      id
      name
      lastName
    }
  }
'''
q_long_vars_newlines = '''
  query (
    $name: String!
    $limit: Integer
  ){
    authors (
      filter: { name: $name }
      limit: $limit
    ) {
      id
      name
      lastName
    }
  }
'''

q_looong_query = '''
  query LotsOfThings(
    $limit: Int!
  ){
    Authors: authors(
      limit: $limit
      filter:{active: true}
    ){
      id
      name
      lastName
      dateOfBirth
      avatar{
        imageUrl
      }
    }
    bp: blogPosts{
    id
      t: title
      name
      body
      blagger: author{
        name
      }
    }
    users{
      id
      name
      email
    }
  }
'''
# ! Wrong short query (no terminating "}")
q_short_bad_term = '{authors{id}'
# ! Wrong short query (no start/end brackets)
q_short_bad_brackets = 'authors{id}'
# ! wrong short query (no content)
q_short_bad_no_content = '{authors{}}'
# ! wrong short query (no query name)
q_short_bad_no_name = '{ { id } }'
# ! wrong short query (no params inside parenthesis)
q_short_bad_no_params = '{authors(){id}}'
# ! wrong long query (no vars inside parenthesis)
q_long_bad_no_vars = 'query (){authors(filter:{name:$name}{id}}'
