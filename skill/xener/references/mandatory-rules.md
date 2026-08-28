# Mandatory Rules

These rules are strict. Violations will cause incorrect behavior or silent
errors. Read this file in full before any operation.

## 1. Use ONLY scripts in `scripts/`

**Why**: The Xener skill is a thin orchestration layer over a complex
bioinformatics toolchain. Bypassing scripts means losing the checkpointing,
parameter validation, and debug_params.yaml reproducibility record that the
official pipeline provides.

**Allowed**:
```bash
python scripts/run_pipeline.py --config config.yaml
python scripts/step1_markers.py --input data.h5ad --cluster-key leiden --outdir output/
python scripts/list_species.py
```

**Forbidden**:
```bash
python -c "from xener import Xener; ..."
python -c "import xener; ..."
python my_custom_script.py
```

**Exception**: Only `python -c "import xener"` is permitted to check
whether xener is installed. No other xener usage is allowed in one-liners.

**Note on `scripts/_xener_init.py`**: this is a *helper module*, not a CLI --
the other scripts import `build_xener()` from it so they all construct the
`Xener` object the same way (and can honor an optional `--init-config`). Do not
run it directly, and do not hand-write your own `Xener(...)` construction to
point at a custom KG / BLAST database. The supported way to use custom
infrastructure is the `--init-config` flag plus `scripts/init_xener.py` to
validate it -- see `workflows/initialization.md`.

## 2. Never pass config via stdin

```bash
# WRONG
python scripts/run_pipeline.py --config /dev/stdin < config.yaml

# CORRECT
python scripts/run_pipeline.py --config /path/to/config.yaml
```

**Why**: stdin-based config passing breaks reproducibility (no record of the
exact config used) and prevents `debug_params.yaml` from being written.

## 2b. Write `config.yaml` as UTF-8, and keep comments ASCII-safe

`run_pipeline.py` now reads the config as UTF-8 explicitly, so plain UTF-8
configs are safe. But be aware of the failure this guards against: on a
non-UTF-8 Windows console (e.g. zh-CN, default code page GBK), a tool that
opens the file with the *platform default* encoding will raise
`UnicodeDecodeError: 'gbk' codec can't decode byte ...` the instant a YAML
comment contains a non-ASCII character -- the classic culprit is an **em-dash
(`--`)** or other "smart punctuation" pasted into a comment.

Practical guidance when composing a config:
- Prefer **ASCII** in comments (`-` instead of `--`, plain quotes). It is the
  one encoding that can never trip this.
- If you do write non-ASCII, ensure the file is saved as UTF-8.
- If you hit a `UnicodeDecodeError` mentioning `gbk`/`cp936`, the fix is the
  config file's bytes, not the pipeline -- rewrite the offending comment as
  ASCII and re-run.

## 3. Always confirm `model_species` and `organ` with the user

Wrong values will cause pipeline failure. Before running, run:

```bash
python scripts/list_species.py
python scripts/list_organs.py
```

Present the available options to the user (categorized by Plants/Animals/etc.,
in 6-column tables -- see main `SKILL.md` for the formatting rule), then
**wait for explicit confirmation** before running the pipeline.

### Animal datasets: `organ: Unknown` is the default -- exception to "always confirm"

The bundled KG only carries **plant** organ taxonomy (Flower / Fruit /
Leaf / Root / Seed / Stem). Animal cell atlases (human, mouse, zebrafish,
etc.) therefore have **no organ value** that the KG would recognize as
anatomically correct. When the inspect step identifies the target as an
animal species (any of the four `Homo_sapiens` / `Mus_musculus` /
`Rattus_norvegicus` / `Danio_rerio` / `Gallus_gallus` /
`Drosophila_melanogaster` / `Caenorhabditis_elegans` / `Macaca_mulatta`,
or `ENSG\d+` / `ENSMUSG\d+` var_names regex), the agent MUST default
`organ: Unknown` (which is a literal accepted value of `list_organs.py`,
disabling the KG organ filter) and **announce** the decision in plain
language -- but it MUST NOT block on a confirmation question. The user's
genepilote rollout request was: *"图谱中的动物都没有明确 organ"* -- do not
ask the user about organ choice for animal datasets when the KG cannot
answer it anyway. This is the only sanctioned deviation from the
"always confirm `organ`" rule.

The agent must NEVER invent a plant organ (Leaf / Root / etc.) for an
animal sample just to satisfy the `list_organs.py` validation -- that
would falsify a HARD constraint (`mandatory-rules.md` Sec. 11). See
`workflows/species-selection.md` -> "Default `organ` for animal
datasets" for the full reasoning and detection rules.

### Self-annotation shortcut (skip_blast) -- exception to "always confirm"

When the inspect step confidently identifies the target as one of the four
well-curated model organisms (`Arabidopsis_thaliana`, `Oryza_sativa`,
`Homo_sapiens`, `Mus_musculus`), the agent MAY auto-set
`model_species: [<that one>]` and `skip_blast: true` -- but must still
**announce the decision in plain language** so the user can override before
running. The rule of thumb:

- **Strong signal (>=2 independent detections)** -- inspect's
  `species_hint`, `uns['organism']`, or var_names regex all agree on one
  of the four -> auto-set `skip_blast: true`, single-entry `model_species`,
  and tell the user: *"Inspection identifies this as X; setting
  `model_species: [X]` and `skip_blast: true`. Override either before
  running if this is wrong."*
- **Mismatch** -- target detected as one of the four but `model_species`
  excludes it -> warn, do NOT silently rewrite. *"Target detected as
  Arabidopsis_thaliana but `model_species: [Homo_sapiens, Mus_musculus]`.
  Confirm cross-species is intended, or add Arabidopsis_thaliana."*
- **Weak / conflicting signal** -- fall back to standard confirmation per
  Sec. 3 above (propose 1-3 candidates, wait for yes/override).

See `workflows/species-selection.md` -> "Self-annotation shortcut" for
the full detection table and worked example.

## 4. Use script-based recovery, not custom code

If a script fails, you may edit the script to fix the bug, then re-run it.
**Do not write new scripts** to work around a failure.

**Why**: Custom scripts bypass checkpointing, `debug_params.yaml`
reproducibility recording, and the centralized validation and `--init-config`
construction path (`_xener_init.py`) that every built-in script enforces.
A one-off script has no logging, no parameter recording, and no way for
subsequent pipeline steps to discover it. Fixing the existing script
preserves the full orchestration contract.

## 5. Config field validation

Before running, the config must satisfy:
- `model_species`: list, each element must be in `scripts/list_species.py` output
- `organ`: string, must be in `scripts/list_organs.py` output
- `non_model_h5ad`, `outdir`: non-empty strings
- `non_model_fasta`: non-empty string **unless `skip_blast: true`**, in which case it may be omitted (the marker's gene IDs then become KG keys directly, and the FASTA is never read).

**Why**: Invalid field values are the most common cause of pipeline failures --
a typo in a species name, a non-existent organ, or a missing output path.
Validating against `list_species.py` / `list_organs.py` output catches these
before the pipeline starts, saving the multi-minute BLAST + KG run.

`xener`'s own `__call__` also enforces the `skip_blast` ↔ `non_model_fasta`
constraint up front (before any step runs), so a missing FASTA never reaches
step 3.

See `workflows/config-validation.md` for the full validation procedure.

## 6. Refinement candidate celltypes must come from step 5 output

`--celltype` arguments to `scripts/refine_cluster.py` must be values that
appear in `celltype_weight.csv` for the target cluster. Do not invent cell
type names -- they will fail at runtime.

## 7. Optional parameters inherit defaults

You do not need to specify every parameter. The pipeline reads defaults
from the package config. Override only when you have a reason.

## 8. Completeness over demonstration

When the user provides a real dataset and asks for cell-type
annotation, the task is **complete-annotation**, not a workflow
demo. The agent must refine **every** cluster where the top-2
distinct `init_weight` ratio is > 0.5 -- not a representative
subset, not a "demonstrably mixed" subset, not a 1-3-cluster
cap. Refining N eligible clusters costs ~N×1 minute and produces
the per-cluster sub-population the user needs. The previous
"pick up to 3" heuristic was a demo-mode leftover and is
**withdrawn** -- see `autonomous-decision-making.md` section"Completeness
vs. demonstration" for the full reasoning.

Specific anti-patterns that violate this rule:

- ❌ Selecting clusters "for lineage coverage" (one vasculature,
  one ground tissue, one root cap) -- that is a presentation
  choice, not an annotation choice.
- ❌ Skipping a high-ratio cluster because the top-2 cell types
  "look biologically unrelated" (e.g. quiescent center + root
  hair cell) -- that unrelatedness is the *reason* to refine; it
  is a signal that the clustering may be bad or that KG
  propagation biased step 5. The refinement is the test.
- ❌ Treating 3/3 uniform refinements as "sufficient evidence" the
  clustering is good -- that is a sample of 3, not the dataset.
- ❌ Capping at any small number to "leave time for visualization"
  or "keep the narrative clean". The user does not pay for agent
  time; do the work.

## 9. Long-running steps: wait by notification, NEVER by `sleep`

The two long steps are the **pipeline** (`run_pipeline.py`) and **batch
refinement** (`refine_cluster.py --plan`). With a warm BLAST cache they finish
in a few minutes; plotting is faster still. How you wait for them matters --
this rule exists because an earlier run wasted ~11 minutes polling with
`sleep N && grep`.

**Run them one of two ways:**

1. **Foreground with a generous Bash `timeout`** (e.g. `timeout: 600000` = the
   10-minute max). Simplest; the call returns when the step is done.
2. **Background** (`run_in_background: true`). The harness **re-invokes you
   automatically when the task completes** -- so after launching, *end your
   turn* and do nothing until that completion notification arrives.

**NEVER do this:**

```bash
# FORBIDDEN: blind sleep-polling
sleep 90 && grep ... outdir/xener.log
```

Why it is wrong:
- `sleep` **blocks your turn**. The completion notification can only be
  processed when you are idle, so sleeping *delays your own reaction* to the
  task finishing.
- It is a **blind timer**: you either sleep too short (read a half-written
  log, then sleep again -- wasted round-trips) or too long (the task finished
  long ago and you are still asleep). A timer cannot align with an event.
- `sleep >= 120` additionally **collides with the Bash command timeout**
  (default 120 000 ms) -- the call is killed with exit 143 and you have waited
  two minutes for nothing. This actually happened.

**Do this instead:**

| Goal | Correct mechanism |
|------|-------------------|
| Just wait for completion | Background the task, then **end your turn**. The completion notification re-invokes you. |
| Wait synchronously, in-turn | `TaskOutput` with `block: true` -- returns the instant the task ends, not on a guessed timer. |
| Peek at progress mid-run | A **bare** `grep outdir/xener.log` with **no** `sleep` prefix. It is instant; an empty result just means "nothing logged yet", which is itself information. Do not wrap it in a poll loop. |
| Come back later without blocking | `ScheduleWakeup` (non-blocking timer), then **end your turn**. Unlike `sleep`, it does not occupy you and does not mask the completion notification. |

The unifying principle: **status checks are instantaneous and need no timer;
waiting is event-driven (notification / `TaskOutput` / `ScheduleWakeup`), never
`sleep`-driven.**

## 10. Inspect the h5ad ONCE; never re-read it when a CSV will do

The target `.h5ad` is frequently multi-GB and a single read (~30-45 s for ~1 GB)
is the **dominant I/O cost of the whole workflow**. Treat each read as expensive.

- **Inspection is a single command:** `python scripts/inspect_h5ad.py --input <h5ad>`.
  It loads the file once and prints everything needed to compose a config
  (cluster_key, species hint, organ hint, cluster sizes, recommended `top_num`,
  `.X`/raw sanity). **Do not** follow it with ad-hoc `python -c "import scanpy;
  sc.read(...)"` reads to fetch "one more field" -- every field is already in
  its output. (This is the *only* sanctioned inline-scanpy path besides rule Sec. 1.)
- **The quality gate does not re-read the h5ad.** `run_pipeline.py` calls the
  gate in-process and the gate derives cluster sizes from the lightweight
  `{dataset}_annotation.csv`, not the h5ad.
- **Plotting does not re-read the h5ad.** `plot_umap.py` takes the same
  annotation CSV (per-cell UMAP coords + labels).

If you find yourself about to call `sc.read()` on the big file a second time,
stop: the answer is almost certainly already in `inspect_h5ad.py`'s output or
in a `*_annotation.csv` / `*.csv` already on disk.

## 11. Hard constraints outrank the quality gate

**A value fixed by the biology of the dataset, by the user, or by the
available infrastructure is a HARD CONSTRAINT. The post-run quality gate
(`check_output.py`, `self-tuning-protocol.md`) is a SOFT SIGNAL -- and it is now
baseline-relative: it never hard-fails a run for being above an advisory target,
only for structural breakage or a regression vs a baseline. Never change a hard
constraint to move a soft signal. Tune SOFT levers to improve the signals; if,
after the best soft-lever choice, a signal is still above target under the
correct hard constraints, that is a documented PASS, not something to "fix" by
falsifying a constraint.**

This rule is data-independent; it applies to every run.

### What is hard vs soft

| HARD constraint -- do NOT change to pass the gate | Why it is hard |
|---|---|
| `organ`, once it reflects a known/confirmed tissue of the sample | Biological fact about the data |
| `cluster_key` | What the h5ad actually contains |
| input `non_model_h5ad` / `non_model_fasta` | The data under analysis |
| any value the **user explicitly set or confirmed** | User intent outranks the agent |
| `model_species` / `organ` membership in the KG + BLAST DB | Infrastructure fact; an absent value cannot run |

Note: `model_species` is **no longer a hard constraint**. The *only* hard fact
about species is the last row -- a species must exist in the KG + BLAST DB to be
usable. *Which* species you pick (clade, distance, count) is a SOFT tuning lever
(see below and the SOFT table).

| SOFT parameter -- tune these freely to improve the gate |
|---|
| **`model_species` entirely -- clade, phylogenetic distance, and count.** Prefer the closest relatives, but when close relatives are absent or shallow in the KG you MAY add more distant species that are well-represented in the KG for the target organ. Constraints: each species must exist in the KG + BLAST DB (hard), and you *add to* the close relatives rather than replacing them. |
| BLAST thresholds: `pident`, `evalue`, `bitscore` |
| `top_num`, `multihomolo`, `homolo_weight_key`, `marker_weight_method` |
| `mode`, `decay_factor`, `threshold`, `ann_strict`, `mapping_strict` |
| `candidate_annotation` (restrict the output cell-type set) |

`model_species` is a SOFT lever in full. There is no hard "phylogenetic
boundary": picking a more distant species is a tuning choice, not a constraint
violation. The trade-off to weigh is *homology validity vs KG coverage* -- a
distant species transfers homology less reliably, so reach for it to **rescue
KG coverage** when closer relatives are missing or KG-shallow, keep the close
relatives in the list as well, and prefer the closest species that has
sufficient KG depth. What you must NOT do to pass the gate is change a HARD
constraint -- turning the `organ` filter off, or moving `organ` to a tissue the
sample is not. Adding a well-covered distant species is a legal soft fix;
changing the confirmed organ is not.

### Protocol when a signal is above target (or the gate fails)

The gate is baseline-relative ("improvement is enough"). A `[WARN]` (above an
advisory target) is **not** a failure -- it is a prompt to tune soft levers.

1. Read the WARN (`self-tuning-protocol.md`) and the exact cause
   (`log-interpretation.md`).
2. Apply a SOFT lever to improve the signal: add a KG-present relative --
   closest first, or a more distant but well-covered species to rescue KG
   coverage; relax BLAST thresholds; raise `top_num`; drop `threshold`;
   restrict `candidate_annotation`; ... Then **re-run with the previous run's
   outdir as `--baseline`.**
3. Read the baseline comparison:
   - **Improved or held** -> the gate PASSES. Adopt the new config. (This is the
     common case: an added KG-rich species that lowers KG miss, even if still
     above 30%, is a legitimate, gate-passing improvement.)
   - **Regressed** -> the gate FAILS. Revert the change; the lever hurt.
4. **Never** reach for a HARD constraint to move the signal -- e.g. "switch
   `organ` away from the sample's real tissue", "set `organ=None`/`Unknown`
   purely to drop the filter". STOP. Keep the hard constraint.
5. If, after the best available soft-lever choice (closest relatives *plus* the
   most KG-rich distant species), the signal is still above target but did not
   regress, the run **PASSES under the correct organ**. Document in
   `outdir/autonomous_log.md`: the residual signal, the species you added and
   from how far out, the measured effect, and that the residual reflects shallow
   KG coverage for that organ (a KG property), not a config bug.

### The organ trap (most common instance)

When mean KG miss is above target (a `[WARN]`), the message says "model_species
too narrow for the chosen organ." Only these responses are legal:

- ✅ Add a KG-present relative (soft) -- closest first, but a **more distant,
  well-covered species is also a legal soft addition** when close relatives are
  missing or KG-shallow (keep the close ones too); OR relax BLAST; OR -- **only
  if `organ` was an unconfirmed guess** -- reconsider the organ. Re-run with a
  `--baseline` and keep the change if it improved or held.
- ❌ Change `organ` to a tissue the sample is NOT, or to `None`/`Unknown`
  purely to lift the filter, **when the organ is a confirmed property of the
  data.** A high KG miss that persists even after you have added the best
  available species (close *and* distant well-covered) usually means the KG is
  simply shallow for that organ -- a property of the KG, not a config error. The
  honest result is a **PASS under the correct organ** with a documented residual
  WARN -- never a gate "rescued" by switching to Root/None.

**Diagnostic tell:** if you applied the species soft lever to its limit --
closest relatives *plus* the most KG-rich distant species available -- and the
metric barely moved, the bottleneck is NOT the species set; it is the organ's
coverage depth in the KG (a hard fact). Keep whichever soft-lever config scored
best (the gate passes it as an improvement/hold vs baseline), document the
residual, and do NOT start changing the confirmed organ. "Barely moved" still
means *moved in the right direction* -> keep it; only a *regression* is a reason
to revert.

### Red flags -- STOP, you are about to violate this rule

- "organ=None / organ=Unknown is THE FIX -- it directly attacks the KG-miss WARN."
- "The docs say 'try a different organ', so changing the tissue is sanctioned."
- "The signal is above target, so the run isn't done; I must hit 30% somehow."
  (No -- above-target is advisory; improving-or-holding vs baseline PASSES.)
- "I correctly diagnosed that organ is the binding lever, therefore I should change organ."
- "Root passes the gate, so I'll annotate this stem sample against Root."

All of these mean: you are trying to move a SOFT signal by breaking a HARD
constraint. Keep the constraint. Improve via soft levers and document the result.

**Not a red flag:** the `organ: Unknown` default for animal datasets
(see Sec. 3 "Animal datasets" exception above) is **not** an "organ=None
hack to lift the KG-miss filter". It is the documented default because
the bundled KG has no anatomically matching organ value for animal
samples. The red-flag clause above targets the post-hoc case of
switching `organ` to `Unknown` *purely to silence a `[WARN]` on a
dataset whose tissue is well-defined* -- that remains a HARD-constraint
violation. Setting `organ: Unknown` up-front because the target is an
animal and the KG has no matching value is fine and is in fact required.

## 12. Pass keyword arguments to every xener API call

Inside every script under `scripts/`, every call into the xener library
(`Xener`-class methods like `get_markers`, `get_gene_weight`, `mapping`,
`get_topk_gene`, `cell_annotation`, `refine_single_cluster`, `run_from_yaml`,
plus the `build_xener()` helper from `_xener_init.py`) MUST use Python keyword
arguments (`arg=value`), never positional ones.

```python
# REQUIRED
markers, _ = annor.get_markers(adata=adata, cluster_key="leiden")
topk, _ = annor.get_topk_gene(
    homolo_weights=homolo_weights,
    top_num=30,
    multihomolo=True,
)
annor = build_xener(init_config=args.init_config)

# FORBIDDEN
markers, _ = annor.get_markers(adata, "leiden")
topk, _ = annor.get_topk_gene(homolo_weights, 30, True)
annor = build_xener(args.init_config)
```

**Why**: xener's API surface is wide and growing, with several parameters that
share a similar type (file paths, int thresholds, bool flags). A positional
call already breaks the moment the upstream signature adds an optional kwarg in
the middle of the parameter list, and a human reviewer cannot tell from a line
like `annor.mapping(markers, "/data/foo.fa", ["Brapa"], "/tmp/out")` which
`str` is the FASTA, the outdir, or something else entirely. The keyword form
makes every call self-documenting and forward-compatible with new optional
parameters that the library may add between releases.

The only exceptions are calls into third-party libraries (`pandas.read_csv`,
`scanpy.read`, `matplotlib`, `networkx`, ...); their calling conventions are
fixed by upstream and changing them is out of scope. The rule covers *every*
call where xener is on the left side of the dot.

When editing a script, treat any existing positional form as a bug to be
converted. New scripts MUST be written in this form from the start.

## 13. Per-user global init-config (`~/.xener/init.yaml`)

If you find yourself passing the same `--init-config <path>` to multiple
scripts on the same machine, write the file once to `~/.xener/init.yaml`
(under your home directory -- the same one that already holds
`.xener/data/default_run_conf.yaml` and `.xener/data/blastdb/`). All
scripts then honor it automatically with no flag.

Resolution order (first non-empty wins, per-key):

  1. `--init-config <path>` or the inlined keys in `config.yaml`
  2. `~/.xener/init.yaml`  (per-user global; overridable via the
     `XENER_GLOBAL_INIT` environment variable)
  3. Built-in defaults (public cloud KG + bundled BLAST database)

Disable the global file for a single run with
`XENER_GLOBAL_INIT="" python scripts/run_pipeline.py …`. This is the
escape hatch for CI jobs and for diagnosing "where did this KG endpoint
come from?" surprises -- it is also what `init_xener.py` reports when it
finds the global file missing.

**Do NOT** put init keys inside `~/.xener/data/` -- that directory is
owned by `xener.config._ensure_data()` and may be repopulated by an
unrelated first-import download. The init file lives next to `data/`,
not inside it, precisely so it cannot be silently overwritten.

**Do** keep comments ASCII-safe in `~/.xener/init.yaml` (see rule Sec. 2b).

## 14. ID-namespace preflight -- marker IDs must match the KG

The marker-->-BLAST-->-KG chain has three string-ID matchings that must
line up:

```
adata.raw.var_names  ==  non_model_fasta header.id  ==  KG Gene.Name
                          (after hyphen->underscore)
```

A mismatch at any step silently collapses the run to zero KG hits.
The most common real-world case is a human/mouse h5ad whose
`var_names` are Ensembl IDs (`ENSG\d+`, `ENSMUSG\d+` -- common in
CellxGene / Tabula Sapiens releases) while the bundled BLAST db is
keyed on HGNC / MGI symbols; `extract_fasta_by_name` then finds
**0 / N markers** and the BLAST query FASTA is empty.

**The agent MUST run an ID-namespace preflight** after
`scripts/inspect_h5ad.py` and before composing `config.yaml`. The
preflight is a single decision tree:

1. Look up the per-species expected format in
   [`data-id-namespace.md`](../data-id-namespace.md). High-coverage
   cases:
   - `Arabidopsis_thaliana` -> TAIR locus `AT\dG\d{5}`
   - `Oryza_sativa` -> MSU `LOC_Os\d{2}g\d{5}`
   - `Homo_sapiens` -> **HGNC symbol** (`TP53`, `CD8A`), NOT Ensembl
   - `Mus_musculus` -> **MGI symbol** (`Trp53`, `Cd8a`), NOT Ensembl
2. Compare against `var_names_sample[:5]` from the inspect output.
   If the prefix does not match, **stop and warn the user** -- do
   not silently let the pipeline produce a 100% KG miss.
3. If `skip_blast: true` is planned, the ID namespace is
   `var_names == KG Gene.Name` with zero tolerance. The four
   self-annotation shortcuts are safe (above); `Zea_mays` and
   `Glycine_max` are **not** (KG coverage is too sparse -- see
   `data-id-namespace.md` -> "BLAST-id-only species").
4. If `non_model_fasta` is supplied, its `record.id` (the first
   whitespace-separated token of each header) must match the
   `var_names` format. Pipeline logs `Extracted N/M sequences from
   <fasta>` -- look for it after step 3. If `N` is dramatically
   lower than `M`, the FASTA is mismatched.

This rule supersedes the post-run `[WARN]` for "mean KG miss" in
one case: the user explicitly accepts a known ID-namespace gap and
documents it (e.g. annotating salmon against zebrafish is a distant
species transfer where the user accepts low coverage). In that
case, the gate `[WARN]` remains advisory; you are still allowed to
proceed, and the rule does not block you -- it only requires the
preflight have been run so the gap was not silently discovered.

For the full per-species reference and common-mismatch table, see
[`data-id-namespace.md`](../data-id-namespace.md). The full
self-probe one-liner is at the bottom of that file.
