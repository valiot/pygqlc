author_activate = '''
  mutation {
    upsertAuthor(findBy: {name: "Elon", lastName: "Musk"}, author: { active: true }) {
      successful
      messages {
        field
        message
      }
      result {
        name
        active
      }
    }
  }
'''

author_set_active = '''
  mutation SetActive($active: Boolean!){
    upsertAuthor(findBy: {name: "Elon", lastName: "Musk"}, author: { active: $active }) {
      successful
      messages {
        field
        message
      }
      result {
        name
        active
      }
    }
  }
'''

update_any_author_active = '''
  mutation SetActive(
    $name: String!
    $active: Boolean!
  ){
    updateAuthor(
      findBy: { name: $name }
      author: { active: $active }
    ) {
      successful
      messages {
        field
        message
      }
      result {
        id
        name
        lastName
        active
        dateOfBirth
        updatedAt
      }
    }
  }
'''

create_author = '''
  mutation CreateAuthor(
    $name: String!
    $lastName: String!
    $active: Boolean
  ){
    createAuthor(
      name: $name
      lastName: $lastName
      active: $active
    ){
      successful
      messages{
        field
        message
      }
      result{
        id
        name
        lastName
        active
      }
    }
  }
'''

bad_author_create = 'mutation {createAuthor(name:"Baruc"){succ}}'
