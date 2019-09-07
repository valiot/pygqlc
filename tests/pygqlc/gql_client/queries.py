get_authors = '''{authors{id name}}'''

bad_get_authors = '''{authors{id name}}}'''

get_authors_siblings = '''
  query Siblings($lastName: String!) {
    authors(filter: { lastName: $lastName }) {
      name
      lastName
    }
  }
'''

get_last_author = '''
  {
    authors(orderBy:{desc:ID} limit:1){
      name
      lastName
    }
  }
'''

get_authors_no_name = '''
  {
    authors(
      filter:{name: "!()"}
      orderBy:{desc: ID} limit: 1
    ){
      name
      lastName
    }
  }
'''
