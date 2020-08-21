class Singleton(type):
  """This class defines another classes to be a singleton.

  Args:
      type (cls): Class that wants to obtain the singleton pattern.
  """
  _instances = {}
  def __call__(cls, *args, **kwargs):
    if cls not in cls._instances:
      cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
    return cls._instances[cls]
