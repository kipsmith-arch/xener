# Post-Run Quality Gate (REQUIRED) — baseline-relative

**This is a mandatory step, not optional polish.** Every xener run, whether
invoked by `run_pipeline.py` or step-by-step, MUST pass through the quality
gate before the run is declared "done".

The gate is **baseline-relative** ("improvement is enough"). It does **not**
hard-fail a run merely for being above an absolute threshold. Its rule is:

```
PASS = structurally sound
       AND ( absolute targets met OR not worsened vs --baseline )
```

- **Absolute targets** (mean KG miss ≤ 30%, severe-miss tail ≤ 5%, ≥ 5 unique
  top-1 cell types) are **advisory**. Being above a target prints a `[WARN]`,
  never a `[FAIL]`. They are goals you tune SOFT levers toward, not blockers.
- The only **HARD failures** are:
  1. **Structural breakage** — `celltype_weight.csv` missing/empty, no cluster
     has annotation rows, or the run log is absent/unparseable.
  2. **Regression vs `--baseline`** — you changed the config and a key signal
     got measurably worse (mean KG miss or severe-miss tail up by > 1pp, or
     unique top-1 types down).
- With **no `--baseline`**, a structurally-sound run PASSES even below target —
  there is nothing yet to improve against. To *prove* a soft-lever change
  helped, re-run with the previous run's outdir as `--baseline`.

> **The old absolute weak-cluster check on `init_weight` (`< 50` for n_cells >
> 200) has been REMOVED.** It was scale-dependent (`init_weight` is an
> unnormalized sum that ranged ~14 to ~1280 across clusters in one real
> dataset) and brittle at its boundary (a cluster at 50.5 flipping to 49.8 from
> a trivial perturbation). Confidence is now judged *relatively* (did a
> soft-lever change improve the signals?), not by an absolute cutoff. Note:
> `init_weight` is **still** used for *refinement* eligibility (top-2 ratio);
> that is a different, scale-invariant ratio and is unaffected.

## Why a gate at all

A run can complete with exit code 0 and still produce biologically useless
annotations — most often because the KG had few edges for the chosen
`model_species` + `organ`, so homologs map to nothing and weights are thin.
The gate surfaces that as a `[WARN]` and, crucially, lets you **measure whether
a fix helped** by comparing against a baseline.

## Tier-0 checks (no ground truth, no baseline required)

The baseline-relative gate below compares a run to its predecessor. On the
**first** run there is no baseline, and ground truth is rarely available.
Path-mode annotation still exposes self-consistency signals on
`celltype_weight.csv` + `*_annotation.csv` that point at chain-bonus /
lineage-drift problems. Any one is a hint; three or more firing on the same
cluster is strong evidence the annotation is wrong even without ground truth.
These run on the first successful run before any baseline exists.

### Tier-0 signals

**A. Top-2 init_weight close + lineages differ.** For each cluster, sort
`celltype_weight.csv` by `init_weight`; flag if top-2 ratio > 0.9 AND the two
belong to different lineages (e.g. `mononuclear phagocyte` vs `basal cell`).
3+ clusters firing ⇒ chain-bonus problem.

**B. path-mode path length ≥ 4.** Length ≥ 4 in `*_annotation.csv['xener']`
means the algorithm walked multiple ancestor hops to reach a winner — usually
the real celltype is a leaf in the KG ontology DAG, so the algorithm fell
back to whichever celltype has the longest chain. > 10 % of clusters firing
⇒ flag.

**C. Convergence to one biologically implausible celltype.** Count final
tokens (`xener.str.split('>').str[-1]`) across clusters. A single token > 15 %
of clusters AND biologically implausible for the dataset's tissue ⇒ flag.
The over-represented celltype is being chosen as a default sink by max-pool
propagation.

**D. Per-cluster KG miss > 70 %.** `grep "total [0-9.]*% homolos" xener.log`
— high miss means init_weight is dominated by a few genes, whose KG edges may
point to an unrelated celltype.

**E. Top-1 init_weight ≠ path start.** In `celltype_weight.csv`, top by
`init_weight` ≠ first segment of `xener` in `*_annotation.csv` ⇒ propagation
overrode gene-level KG signal. Direct fingerprint of chain bonus.

### Tier-0 triage rule

When ≥ 3 of signals A–E fire on ≥ 3 clusters:

1. **Add `candidate_annotation`** (cheapest, safest) — see selection procedure
   below.
2. **`mode: path` → `mode: node`** — bypass celltype2celltype propagation.
   Loses ontology-tracing strength.
3. **`decay_factor` 0.7 → 0.3** — weaken chain bonus without abandoning
   path-mode.
4. **Do not** touch `mapping_strict` or `organ` — HARD constraints
   (mandatory-rules.md §11).

All four levers can be tuned without ground truth. Evaluation requires
wet-lab validation or a held-out set.

### Selecting the `candidate_annotation` list

The list must contain celltypes biologically expected in the dataset's
tissue. Wrong values are asymmetric: missing a real type silently mislabels
its cluster; adding an unrelated type re-introduces chain bonus. Goal is
**maximum recall on real tissue types, maximum rejection of unrelated
lineages**.

#### Sources (no ground truth needed)

1. **Dataset metadata.** `adata.obs['tissue']` + `uns['organism']` anchor the
   tissue. CL/UBERON IDs → OLS lookup → expected cell-type children.
2. **First-run `celltype_weight.csv` (recommended).** Empirical inventory of
   what the KG emitted. Partition by lineage using the bags below:

   ```python
   LIN_IMMUNE = {'microglial cell', 'macrophage', 'monocyte',
                 'mononuclear phagocyte', 'natural killer cell',
                 'lymphocyte', 'T cell', 'B cell', 'dendritic cell',
                 'plasma cell', 'myeloid cell', 'leukocyte',
                 'professional antigen presenting cell'}
   LIN_EPI = {'epithelial cell', 'basal cell', 'ciliated cell',
              'secretory cell', 'lung secretory cell', 'club cell',
              'goblet cell', 'ionocyte',
              'pulmonary alveolar type 2 cell', 'pulmonary alveolar type 1 cell'}
   ```

   Add `LIN_STROMA`, `LIN_ENDO`, `LIN_NEURO` as needed.
3. **KG inventory.** `xener.KG.get_species_organ_cell()` filtered to target
   species/organ — upper bound of what KG could ever return. Cross-check
   source 2 against this; drop types not in the inventory.
4. **External references (advisory).** Cell Ontology browser, PanglaoDB,
   `adata.uns['citation']`. For borderline types.

#### Procedure

1. `inspect_h5ad.py` → tissue + organism.
2. First `run_pipeline.py` (no restriction) → populates
   `celltype_weight.csv`.
3. Partition celltypes by lineage.
4. For non-immune-tissue datasets: KEEP LIN_EPI + "other" with
   `init_weight > 1000`; DROP LIN_IMMUNE + "other" with `init_weight < 100`
   (KG noise).
5. Cross-check against source 3; drop types not in KG inventory.
6. Write list, re-run with `--baseline <prev_outdir>`.

#### When NOT to use `candidate_annotation`

- **Blood / immune tissue**: every celltype IS immune. Flip the rule —
  LIN_IMMUNE is the candidate set. Manual curation needed.
- **Cross-species annotation** with unknown target celltypes:
  over-restricting hides real types. Prefer `mode: node` or
  `decay_factor: 0.3` instead.
- **Discovery / atlas-building**: restriction defeats the purpose.

#### Validation

After setting `candidate_annotation`, re-run with `--baseline`:

- Signal C should drop to near-zero.
- Signal E should drop sharply.
- Cluster-level accuracy (if ground truth) should rise.

Regression ⇒ list too narrow; expand and re-run.

### Limitations of Tier-0 signals

These signals catch **chain-bonus / lineage-drift** specifically. They do
**not** catch:

- Wrong `model_species` (uniformly high KG miss, Signal D everywhere).
- Wrong `organ` when KG has a non-`Unknown` value for the tissue (no lineage
  mismatch; need external sanity check vs `adata.uns['organism']`).
- True mixed-lineage clusters (doublets) where chain bonus lands on a
  correct ancestor — refine is the right tool.
- Stale / incomplete KG ontology edges (Signal B can fire on legitimately
  long chains).

## Signals the gate computes

Run `scripts/check_output.py --outdir <outdir> [--baseline <prev_outdir>]`
(or let `run_pipeline.py` call it in-process).

| Signal | Source | Advisory target | Role |
|--------|--------|-----------------|------|
| Mean KG miss (per cluster) | `total X% homolos of organ[...] not in kg` in the log | ≤ 0.30 | primary, comparable |
| Severe-miss tail | same | ≤ 5% of clusters > 0.80 | comparable |
| Unique top-1 cell types | `celltype_weight.csv` | ≥ 5 (when > 10 clusters) | comparable |
| Annotation rows present | `celltype_weight.csv` | every cluster | **structural floor** |

Each run writes these to `<outdir>/gate_metrics.json` so a later run can be
compared against it.

## The intended response to a `[WARN]` (mandatory-rules.md §11)

A high mean KG miss is almost always `model_species` being too narrow / shallow
for the organ. The fix is a **SOFT lever**, and the gate now *rewards* it:

1. **Add a KG-present relative to `model_species`** — closest first; or, when
   close relatives are absent or KG-shallow for the organ, a **more distant but
   well-covered species** (e.g. Arabidopsis for a plant stem). `model_species`
   has no hard phylogenetic boundary. Keep the close relatives in the list.
2. Re-run from Step 3 (reuse `marker_gene.csv` / `marker_weight.csv`), passing
   the **previous run's outdir as `--baseline`**.
3. If the signal **improved (or held)** → the gate PASSES; adopt the new
   config. If it **regressed** → the gate FAILS; revert.

Other soft levers: relax BLAST (`pident`/`evalue`/`bitscore`), raise `top_num`,
adjust `threshold`/`decay_factor`/`mode`, restrict `candidate_annotation` (see
"Selecting the `candidate_annotation` list" above).

> **The HARD constraints are never touched to move a signal.** The gate does
> not read `organ` and cannot be passed by changing it. Switching a stem sample
> to Root, or to `None`/`Unknown` just to drop the filter, is the **organ
> trap** — forbidden by `mandatory-rules.md` §11 even though it would lower KG
> miss. If, after adding the best available species (close *and* distant
> well-covered), the mean KG miss is still above target but did not regress, the
> run **PASSES** under the correct organ; the residual is shallow KG coverage
> for that organ, documented in `autonomous_log.md`, not a config bug to chase.

## What the gate looks like in practice

```bash
# First run (no baseline): structurally sound, below target -> PASS (advisory).
$ python scripts/check_output.py --outdir output/edf_v1/
[INFO] structure: 36 clusters have annotation rows.
[WARN] signal: mean KG miss 47.4% ABOVE target 30%. Soft fix: add a KG-rich
       relative to model_species ... Never change a confirmed organ (§11).
[INFO] signal: 3 unique top-1 cell types across 36 clusters
Quality gate PASSED: PASSED (below target; no baseline to judge improvement).

# Re-run after adding a KG-rich species, compared to the first run.
$ python scripts/check_output.py --outdir output/edf_v2/ --baseline output/edf_v1/
[INFO] baseline: mean KG miss 47.4% -> 31.2% (improved)
[INFO] baseline: unique top-1 types 3 -> 9 (improved)
Quality gate PASSED: PASSED (improved vs baseline).
```

## Automatic invocation

`run_pipeline.py` calls the gate at the end, in-process. Pass `--baseline
<prev_outdir>` to `run_pipeline.py` to forward it to the gate. The pipeline
exits non-zero only on a **structural** failure or a **regression** vs the
baseline — not for being above an advisory target.

## Manual re-run shortcut (improve, then compare)

```bash
# v1 (baseline): closest relatives only.
python scripts/run_pipeline.py --config config_v1.yaml --init-config init.yaml

# v2: add a KG-rich (possibly distant) species, compare to v1.
python scripts/run_pipeline.py --config config_v2.yaml --init-config init.yaml \
    --baseline output/edf_v1
# Gate PASSES iff v2 improved-or-held vs v1 (and is structurally sound).
```

Or run the steps individually (reuse `marker_weight.csv`) and call
`check_output.py --outdir output/edf_v2 --baseline output/edf_v1` at the end.

## Legacy "self-tuning" guidance

The original heuristics (e.g. "if median init_weight is low, re-run with
`--threshold null --decay-factor 0.5`") still apply as **second-line soft-lever
adjustments**. Apply one, re-run with the prior run as `--baseline`, and keep
the change only if the gate confirms the signals improved or held.
