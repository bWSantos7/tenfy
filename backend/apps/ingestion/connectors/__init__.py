from . import base    # noqa
from . import cbt     # noqa
from . import cosat   # noqa
from . import fct     # noqa
from . import fpt_sp  # noqa
from . import itf     # noqa
from . import utr     # noqa

# Re-export registry helpers so callers can do:
#   from apps.ingestion.connectors import registered_connectors, register_connector
from .base import register_connector, registered_connectors  # noqa: F401

__all__ = [
    'base', 'cbt', 'cosat', 'fct', 'fpt_sp', 'itf', 'utr',
    'register_connector', 'registered_connectors',
]
# CBTYouthConnector is registered in cbt module alongside CBTPublicConnector
# FPTSPKidsConnector is registered in fpt_sp module alongside FPTSPPublicConnector
