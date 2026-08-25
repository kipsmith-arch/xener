#!/usr/bin/env python3
"""Shared Xener-construction helper for the skill's scripts.

NOT a CLI entry point — this module is imported by the other scripts; do not
run it directly. (To test a custom configuration, use ``init_xener.py``.)

Why this module exists alongside ``xener.utils.init_config``
-----------------------------------------------------------
The actual resolution of ``~/.xener/init.yaml`` / ``XENER_GLOBAL_INIT`` /
built-in defaults lives in ``xener.utils.init_config`` so that direct
programmatic callers (``Xener(...)``, ``Xener.run_from_yaml(...)``,
notebooks, third-party scripts) get the same fallback chain as the skill
scripts. This module is just the thin CLI glue:

  * ``build_xener()`` — wraps the package helper with script-friendly
    error handling and returns a ``(Xener, source)`` tuple so each
    script can report what it loaded.
  * ``add_init_config_arg()`` — registers the shared ``--init-config``
    flag on an argparse parser so every script's ``--help`` is identical.
  * ``load_init_config()`` / ``INIT_CONFIG_KEYS`` — re-exported from the
    package so legacy imports keep working.
  * ``global_init_path()`` / ``global_init_exists()`` — re-exported for
    the same reason.

Resolution order (handed off to ``xener.utils.init_config``):

  1. Explicit ``--init-config <path>`` (or the dict equivalent).
  2. ``~/.xener/init.yaml``  (per-user global; overridable via
     ``XENER_GLOBAL_INIT``; set that env var to ``""`` to disable).
  3. ``Xener()`` built-in defaults — public cloud KG + bundled BLAST DB.

Backward compatible: with no init config and no ``~/.xener/init.yaml``,
``build_xener()`` is exactly ``Xener()`` — the public cloud KG plus the
bundled BLAST database, as before.

See references/workflows/initialization.md for the full workflow.
"""

from xener.utils.init_config import (
    INIT_CONFIG_KEYS,
    ResolvedInitConfig,
    global_init_exists,
    global_init_path,
    load_init_config,
    resolve_init_kwargs,
)


def add_init_config_arg(parser):
    """Register the shared ``--init-config`` flag on an argparse parser.

    Call this in every script that builds a Xener so the flag — and its help
    text — stays identical everywhere.
    """
    parser.add_argument(
        "--init-config", default=None, metavar="PATH",
        help="Path to an init-config YAML describing WHERE Xener gets its data "
             "(KG_url / KG_usr / KG_pwd, blastdb_path, blastp_result_path, "
             "blastp_path). "
             "Resolution order: this flag (if given) > per-user global at "
             "~/.xener/init.yaml (overridable via XENER_GLOBAL_INIT, set "
             "that env var to \"\" to disable) > built-in defaults. "
             "See references/workflows/initialization.md.",
    )


def build_xener(init_config=None):
    """Construct a ``Xener`` instance, optionally from a user init-config.

    Parameters
    ----------
    init_config : str | dict | None
        Path to an init-config YAML, an already-parsed dict of the same
        keys, or ``None`` for the per-user global / built-in defaults.

    Returns
    -------
    tuple[xener.Xener, str]
        The constructed ``Xener`` instance and a short label describing
        which init-config source was used (``"explicit"``,
        ``"global"``, or ``"defaults"``). The label is purely
        informational; the Xener object is the main result.

    Notes
    -----
    Tolerant of partial configs: a config that sets only ``KG_url`` keeps
    the bundled BLAST DB, etc.
    """
    from xener import Xener

    resolved: ResolvedInitConfig = resolve_init_kwargs(init_config)

    return Xener(
        kg_kwargs=resolved.kg_kwargs,
        blastdb_path=resolved.blastdb_path,
        blastp_result_path=resolved.blastp_result_path,
        blastp_path=resolved.blastp_path,
    ), resolved.source
