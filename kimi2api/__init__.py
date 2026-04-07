"""
Kimi2API - Kimi Web API Python client.
"""

from .client import Kimi2API, KimiAPIError, create_client, detect_token_type
from .server import create_app

__version__ = "1.2.0"
__all__ = ["Kimi2API", "KimiAPIError", "create_app", "create_client", "detect_token_type"]
