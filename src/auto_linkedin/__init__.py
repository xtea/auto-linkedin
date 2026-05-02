"""auto-linkedin: publish to LinkedIn company pages from the command line."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("auto-li")
except PackageNotFoundError:  # pragma: no cover — happens only in raw checkouts
    __version__ = "0.0.0+local"
