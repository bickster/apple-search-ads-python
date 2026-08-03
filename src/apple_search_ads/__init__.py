"""
Apple Search Ads Python Client

A Python client library for Apple Search Ads API v5.
"""

from importlib import metadata

from .client import AppleSearchAdsClient

# Derived from the installed dist so it can never drift from pyproject.toml
# (release.sh bumps only setup.py/pyproject.toml, never this file).
try:
    __version__ = metadata.version("apple-search-ads-client")
except metadata.PackageNotFoundError:  # source tree without an installed dist
    __version__ = "0.0.0.dev0"

__author__ = "Your Name"
__email__ = "your.email@example.com"

__all__ = ["AppleSearchAdsClient"]
