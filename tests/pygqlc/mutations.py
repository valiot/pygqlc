author_activate = '''
  mutation {
    upsertAuthor(name: "Paulinna", author: { active: true }) {
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
    upsertAuthor(name: "Paulinna", author: { active: $active }) {
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

bad_author_create = 'mutation {createAuthor(name:"Baruc"){succ}}'