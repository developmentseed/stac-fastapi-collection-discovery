"""stac_fastapi.collection_discovery"""

from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version(__name__)
except _PackageNotFoundError:
    __version__ = "unknown"
