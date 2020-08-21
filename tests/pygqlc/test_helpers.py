from pygqlc.GraphQLClient import safe_pop
from pygqlc.helper_modules.Singleton import Singleton

def test_safe_pop_first():
  data = [3, 4, 5]
  datum = safe_pop(data, 0)
  assert datum == 3, \
    'Datum should be the first element'

def test_safe_pop_last():
  data = [3, 4, 5]
  datum = safe_pop(data, -1)
  assert datum == 5, \
    'Datum should be the last element'

def test_safe_pop_empty():
  datum = safe_pop([])
  assert datum is None, \
    'return value should be None by default'

def test_safe_pop_empty_default():
  datum = safe_pop([], default=0)
  assert datum == 0, \
    'return value should be 0 by default'


def test_safe_pop_index_default():
  data = [3, 4, 5]
  datum = safe_pop(data)
  assert datum == 3, \
    'return value should be the first element by default'

def test_singleton_cannot_be_instantiated_twice():
  class UselessLetterClass(metaclass=Singleton):

    def __init__(self, letter='G'):
      self.letter = letter

  first_instance = UselessLetterClass('A')   # First call: actually creates a new instance
  second_instance = UselessLetterClass() # Second call: returns the cached instance
  assert first_instance is second_instance, \
    'Should be the same instance'
  del Singleton._instances[UselessLetterClass]  # Throw away the cached instance
  third_instance = UselessLetterClass()   # Third call: no cached instance, so create one
  assert first_instance is not third_instance, \
    'Should be a different instance'
