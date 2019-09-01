sub_author_updated = '''
  subscription{
    authorUpdated{
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

sub_author_created = '''
  subscription{
    authorCreated{
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
