"""Single-source-of-truth for the xener package version.

This file holds ``__version__`` literally so the running package always
has a usable version attribute — including when the package is loaded
from a source checkout that has NOT been ``pip install``-ed (so
``importlib.metadata.version("xener")`` cannot find it).

The authoritative version is still ``[project].version`` in
``pyproject.toml`` (which is what gets installed into the wheel's
metadata). When ``importlib.metadata`` can find it, ``xener.__init__``
prefers that value over this file, so a wheel install of
``xener-0.1.18`` will report ``0.1.18`` even if this file is stale.

Update protocol:
    1. Bump ``version`` in ``pyproject.toml``.
    2. Bump the constant below to match.
    3. Commit both in the same change.

If you forget step 2, a source checkout reports the old version
(importlib.metadata is unavailable there), but a ``pip install``-ed
copy reports the new one — the latter wins by design.
"""
__version__ = "0.1.17"
