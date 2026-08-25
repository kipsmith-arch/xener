"""xener — cross-species single-cell cell type annotation.

Public API
----------
Xener
    The annotation engine. Construct one and call it (or use
    ``run_from_yaml``) to annotate a dataset.

__version__
    The running version of the package. Resolved lazily on first access:
    wheel metadata (``importlib.metadata.version("xener")``) wins when
    available, otherwise the literal pinned in ``xener/_version.py``.
    Lazy resolution keeps ``import xener`` immune to a missing or broken
    metadata database. See ``xener/_version.py`` for the update protocol.
"""
from .config import _ensure_data

from .core import Xener

__all__ = ["Xener", "__version__"]


def __getattr__(name):
    """Resolve ``__version__`` on first access.

    Priority:
      1. ``importlib.metadata.version("xener")`` — the version actually
         installed via wheel (avoids reporting a stale _version.py
         literal when ``pip install -U xener`` has moved on).
      2. ``xener/_version.py`` — the literal pinned for this checkout,
         used when there's no installed metadata (e.g. running from a
         source clone without ``pip install -e .``).

    A module-level ``__version__`` is intentionally NOT set so that this
    __getattr__ path is the only resolver. (Setting both would let the
    eager value shadow the lazy one.)
    """
    if name == "__version__":
        try:
            from importlib.metadata import PackageNotFoundError, version as _metadata_version
            return _metadata_version("xener")
        except PackageNotFoundError:
            from ._version import __version__ as _literal
            return _literal
        except Exception:
            # Any other importlib.metadata failure (broken cache, exotic
            # environment): still fall through to the literal rather than
            # break ``import xener`` for the user.
            from ._version import __version__ as _literal
            return _literal
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
