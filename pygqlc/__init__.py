from .__version__ import __version__
from .GraphQLClient import GraphQLClient, GQLResponseException
from .QueryParser import QueryParser
from .MutationParser import MutationParser
from .SubscriptionParser import SubscriptionParser
from .helper_modules.Singleton import Singleton

# * Package name:
name = 'pygqlc'
