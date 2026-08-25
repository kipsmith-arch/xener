"""Per-user global init-config resolution for the xener package.

This module is the SINGLE place that knows about ``~/.xener/init.yaml`` and
the ``XENER_GLOBAL_INIT`` environment variable. It exposes a small, pure
``resolve_init_kwargs()`` function that callers (the package itself or any
embedder) use to fill in their init-related constructor arguments when the
caller did not pass them explicitly.

The file lives in the package (``xener.utils.init_config``) — NOT in the
agent skill — because the resolution rule applies equally to:

  * direct programmatic callers (``Xener(...)``, ``Xener.run_from_yaml(...)``,
    notebook usage, third-party scripts), AND
  * the skill's CLI entry points (``scripts/run_pipeline.py``,
    ``scripts/step*.py``, ``scripts/init_xener.py``).

Both layers used to disagree about where init-config came from. With this
module, they share the exact same fallback chain.

Resolution order (first non-empty wins, per-key):

  1. ``init_config`` argument explicitly passed by the caller
     (``str`` path, ``dict`` content).
  2. ``~/.xener/init.yaml``  (per-user global).
  3. Built-in defaults — public cloud KG + bundled BLAST database.

Override & disable:

  * Set ``XENER_GLOBAL_INIT=/some/path.yaml`` to point at a shared file.
  * Set ``XENER_GLOBAL_INIT=""`` to disable the global-file fallback
    entirely (used by CI and by tests).

Where the file lives and why:

The global file lives at ``~/.xener/init.yaml`` — *sibling* of the
existing ``~/.xener/data/`` directory that holds the bundled BLAST DB
and the downloaded ``default_run_conf.yaml``. The ``data/`` directory is
managed by ``xener.config._ensure_data()`` and may be wiped and
repopulated by an unrelated first-import download; the init file is a
user file and is never written or deleted by xener.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import yaml

# Init-config keys that may be set in an init-config YAML — either a
# separate --init-config file, an inlined section of config.yaml, or
# the per-user global at ~/.xener/init.yaml.
INIT_CONFIG_KEYS: tuple[str, ...] = (
    "KG_url",
    "KG_usr",
    "KG_pwd",
    "blastdb_path",
    "blastp_result_path",
    "blastp_path",
)


def global_init_path() -> Optional[Path]:
    """Return the per-user global init-config path (does not require it to exist).

    Honors the ``XENER_GLOBAL_INIT`` environment variable so CI jobs can
    redirect to (or disable via an explicit empty path) the per-user file.
    Returns ``None`` only when ``XENER_GLOBAL_INIT`` is set to an empty
    string — used by tests and CI to force a "defaults-only" run.
    """
    env = os.environ.get("XENER_GLOBAL_INIT")
    if env is not None:
        if env == "":
            return None
        return Path(env).expanduser()
    return Path.home() / ".xener" / "init.yaml"


def global_init_exists() -> bool:
    """True iff the per-user global init-config exists and is a regular file."""
    p = global_init_path()
    return p is not None and p.exists() and p.is_file()


@dataclass(frozen=True)
class ResolvedInitConfig:
    """Outcome of ``resolve_init_kwargs``.

    Attributes
    ----------
    kg_kwargs : dict | None
        KG connection info, ready to pass to ``Xener(kg_kwargs=...)``; or
        ``None`` to keep the cloud default.
    blastdb_path : str | None
        Path to a local BLAST protein DB directory, or ``None`` to keep
        the bundled default.
    blastp_result_path : str | None
        BLASTP result cache directory, or ``None`` to disable the cache.
    blastp_path : str | None
        Path to a ``blastp`` executable (or its containing directory),
        or ``None`` to use the system ``blastp`` from ``$PATH``.
    source : str
        One of ``"explicit"`` (caller passed init_config), ``"global"``
        (loaded from ``~/.xener/init.yaml``), or ``"defaults"`` (no init
        source available — built-in cloud KG + bundled BLAST).
    source_path : str | None
        Filesystem path of the source when ``source in {"explicit", "global"}``,
        for diagnostic reporting; ``None`` for ``"defaults"``.
    """
    kg_kwargs: Optional[dict]
    blastdb_path: Optional[str]
    blastp_result_path: Optional[str]
    blastp_path: Optional[str]
    source: str
    source_path: Optional[str]


def load_init_config(path: Union[str, Path]) -> dict:
    """Read and lightly validate an init-config YAML; return a dict.

    Decoded as UTF-8 explicitly (see ``mandatory-rules.md`` §2b) so a
    non-ASCII comment never trips the platform-default codec on a zh-CN
    Windows console. Unknown keys are not fatal — the user may keep notes
    in the file — but are reported so a typo (e.g. ``KG_URL``) doesn't
    silently get ignored.
    """
    with open(str(path), "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError(
            f"init-config {path} must be a YAML mapping (key: value pairs); "
            f"got {type(cfg).__name__}."
        )
    unknown = set(cfg) - set(INIT_CONFIG_KEYS)
    if unknown:
        # Use ``print`` (not the logger) because this runs at module load
        # in the skill and the warning should appear before any logging
        # configuration is set up.
        print(
            f"[WARN] init-config {path}: ignoring unrecognized key(s) "
            f"{sorted(unknown)}. Known keys: {list(INIT_CONFIG_KEYS)}."
        )
    return cfg


def _orphan_kg_credentials(cfg: dict) -> None:
    """Warn when KG_usr / KG_pwd are set without KG_url."""
    if cfg.get("KG_url"):
        return
    orphan_keys = [k for k in ("KG_usr", "KG_pwd") if cfg.get(k)]
    if orphan_keys:
        print(
            f"[WARN] init-config: {orphan_keys} provided but KG_url is "
            "missing — KG credentials are ignored. Set KG_url to use a "
            "custom Knowledge Graph, or remove the orphan keys to keep the "
            "public cloud KG."
        )


def resolve_init_kwargs(
    init_config: Union[str, Path, dict, None] = None,
) -> ResolvedInitConfig:
    """Resolve which init values ``Xener.__init__`` should use.

    Resolution order (first non-empty wins):

      1. The ``init_config`` argument (path string, dict, or ``None``).
      2. ``~/.xener/init.yaml``  (overridable via ``XENER_GLOBAL_INIT``;
         set that env var to ``""`` to disable).
      3. Built-in defaults — represented by all-None fields, which makes
         ``Xener.__init__`` keep its hardcoded cloud KG + bundled BLAST
         behaviour.

    Per-key tolerance: a partial config (say, only ``KG_url``) keeps the
    bundled BLAST DB and the system ``blastp`` for the other fields —
    same as before this resolver existed.

    The returned ``ResolvedInitConfig`` is pure data: callers pass
    ``kg_kwargs`` / ``blastdb_path`` / ``blastp_result_path`` /
    ``blastp_path`` straight through to ``Xener.__init__``. The
    ``source`` and ``source_path`` attributes are diagnostic only — they
    let CLI wrappers (and ``Xener.__init__``'s own logging) report which
    init-config the run actually honored.
    """
    cfg: Optional[dict] = None
    source_path: Optional[str] = None

    if init_config is None:
        # Fallback to per-user global if present.
        if global_init_exists():
            gp = global_init_path()
            assert gp is not None  # for type checkers
            cfg = load_init_config(gp)
            source_path = str(gp)
            source = "global"
        else:
            source = "defaults"
    elif isinstance(init_config, dict):
        cfg = init_config
        source = "explicit"
    else:
        # init_config is a path.
        cfg = load_init_config(init_config)
        source_path = str(init_config)
        source = "explicit"

    if cfg is not None:
        _orphan_kg_credentials(cfg)

    # Build ``kg_kwargs`` only when the user actually specified a KG
    # endpoint; ``None`` leaves Xener.__init__ to use its default cloud url.
    kg_kwargs: Optional[dict] = None
    if cfg and cfg.get("KG_url"):
        kg_kwargs = {
            "url": cfg["KG_url"],
            "usr": cfg.get("KG_usr"),
            "pwd": cfg.get("KG_pwd"),
        }

    return ResolvedInitConfig(
        kg_kwargs=kg_kwargs,
        blastdb_path=(cfg or {}).get("blastdb_path"),
        blastp_result_path=(cfg or {}).get("blastp_result_path"),
        blastp_path=(cfg or {}).get("blastp_path"),
        source=source,
        source_path=source_path,
    )
