from .GraphQLClient import GraphQLClient
from .QueryParser import QueryParser
from .MutationParser import MutationParser
from .SubscriptionParser import SubscriptionParser
from .helper_modules.Singleton import Singleton

# * Package name:
name = 'pygqlc'
# * required here for pypi upload exceptions:
from .__version__ import __version__
