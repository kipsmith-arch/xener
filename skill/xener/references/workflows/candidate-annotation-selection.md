# Selecting `candidate_annotation` values

`candidate_annotation` is a `list[str]` config field that restricts the
cell-type set the KG may emit. Once set, only listed types participate
in path-mode propagation — every other celltype is filtered out before
gene→celltype propagation. It is the cheapest and most direct lever
for chain-bonus / lineage-drift problems (`autonomous_signals.md` Signal
A/C/E). This document describes **how to determine the list** when
ground-truth labels are not available.

The list must contain cell-type strings that are **biologically expected
to appear in the dataset's tissue**. Wrong values are
asymmetric in cost:

- **Missing a real celltype** → its cluster gets a wrong label (silent
  accuracy loss).
- **Adding an unrelated celltype** → it stays in the candidate set,
  re-introducing the original chain-bonus problem.

So the goal is **maximum recall on real tissue celltypes, maximum
rejection of unrelated lineages** — not exhaustive enumeration.

## Input sources (no ground truth required)

### Source 1 — Dataset metadata (always available)

`inspect_h5ad.py` already extracts:

- `adata.obs['tissue']` — `{'epithelial cell of lung': 10212, 'lung': 5594}`
- `adata.uns['organism']` — `'Homo sapiens'`
- `adata.obs['cell_type']` / `level_*` — only when present, sometimes
  noisy. Treat as **hints**, not truth.

The tissue value is the primary anchor. For Cell Ontology (`CL:*`) and
Uberon (`UBERON:*`) IDs in `adata.obs['tissue_ontology_term_id']`, an
external lookup (OBO files, https://www.ebi.ac.uk/ols) maps the term to
its expected cell-type children — those children are your starting list.

### Source 2 — First-run `celltype_weight.csv` (recommended)

After an initial `run_pipeline.py` run, `celltype_weight.csv` contains
**every celltype the KG emitted for this dataset, with init_weight and
propagation weight per cluster**. This is the empirical "what does the
KG know about my data" inventory.

Recipe (run from the agent skill's Python, no ground truth needed):

```python
import pandas as pd
cw = pd.read_csv('<run>/celltype_weight.csv')
all_types = set(cw['celltype'])

# Partition by lineage. Use the LIN_IMMUNE / LIN_EPI / LIN_STROMA / LIN_ENDO
# bags from autonomous_signals.md as starter lineage tags, then refine
# per tissue.
LIN_IMMUNE = {'microglial cell', 'macrophage', 'monocyte', 'mononuclear phagocyte',
              'natural killer cell', 'lymphocyte', 'T cell', 'B cell',
              'dendritic cell', 'plasma cell', 'myeloid cell', 'leukocyte',
              'professional antigen presenting cell'}
LIN_EPI = {'epithelial cell', 'basal cell', 'ciliated cell', 'secretory cell',
           'lung secretory cell', 'club cell', 'goblet cell', 'ionocyte',
           'pulmonary alveolar type 2 cell', 'pulmonary alveolar type 1 cell'}

def lineage(ct):
    if ct in LIN_IMMUNE: return 'immune'
    if ct in LIN_EPI:    return 'epithelial'
    return 'other'

# Build the candidate list: KEEP epithelial + "other" tissue-relevant
# celltypes, REJECT immune (unless the dataset is blood/immune tissue).
tissue_relevant = [ct for ct in all_types if lineage(ct) != 'immune']
# Sanity-check: print counts per lineage
print(cw['celltype'].apply(lineage).value_counts())
```

For a lung atlas the resulting list typically contains ~10–15 celltypes.
For a brain atlas ~20. For blood/immune tissue ~15.

### Source 3 — KG's own species/celltype inventory

`xener.KG.get_species_organ_cell()` returns the full `(species, organ,
cell)` table — every celltype the KG knows for any species. Filter to the
target species and the relevant organ(s):

```python
soc = annor.KG.get_species_organ_cell()
my_celltypes = set(
    soc[(soc['species'] == 'Homo_sapiens')
        & (soc['organ'].isin(['Unknown']))]  # organ=Unknown for animal atlases
    ['cell']
)
```

This gives a more conservative list than Source 2 (only celltypes the
KG actually has gene→celltype edges for). For self-annotation
(`skip_blast: true`) it is the **upper bound** of what the KG could ever
return for this dataset.

### Source 4 — Tissue-specific celltype references (advisory)

When Sources 1–3 leave ambiguity (e.g. "is `ionocyte` expected in
lung?"), cross-check against:

- Cell Ontology browser (https://www.ebi.ac.uk/ols/ontologies/cl)
- PanglaoDB (https://panglaodb.se) — tissue → marker → celltype tables
- The original publication of the dataset (often in `adata.uns['citation']`)

These are **advisory** — useful when the agent is unsure whether to
include a borderline type, not a primary source.

## Decision procedure (autonomous)

```
1. Run inspect_h5ad.py. Extract tissue + organism.
2. Run run_pipeline.py ONCE without candidate_annotation.
   (The first run populates celltype_weight.csv.)
3. Read celltype_weight.csv. Partition celltypes by lineage.
4. For non-immune-tissue datasets:
     - KEEP: all LIN_EPI celltypes seen
     - KEEP: any "other" celltype with init_weight > 1000 in any cluster
     - DROP: all LIN_IMMUNE celltypes (and any "other" celltypes with
             init_weight < 100 — these are KG noise)
5. Cross-check the resulting list against Source 3 (KG inventory).
   Drop any celltype NOT in the KG inventory (it cannot be returned
   anyway; having it in candidate_annotation has no effect).
6. Write the list to config.yaml. Re-run with --baseline <prev_outdir>.
```

### Worked numbers (Human.h5ad lung atlas)

Source 2 partition of `celltype_weight.csv` unique celltypes:

| Lineage | count | Example types |
|---|---:|---|
| epithelial (KEPT) | ~10 | basal cell, secretory cell, ciliated cell, club cell, goblet cell, ionocyte, pulmonary alveolar type 2 cell, lung secretory cell, neuroendocrine cell, epithelial cell |
| immune (DROPPED) | ~15 | mononuclear phagocyte, monocyte, macrophage, microglial cell, natural killer cell, T cell, B cell, dendritic cell, plasma cell, ... |
| other | ~25 | mostly noise (single-gene hits with init_weight < 100), dropped |

Resulting `candidate_annotation` list: ~10–15 entries. This is what
fixed the chain-bonus issue on this dataset (`output/Human/autonomous_signals.md`).

## When NOT to use `candidate_annotation`

- **Blood / immune tissue datasets** — every celltype IS immune. The
  LIN_IMMUNE bag is the candidate set, not a drop list. Flip the rule.
  Manual curation per dataset is required.
- **Cross-species annotation** where you don't know what celltypes the
  target species has — over-restricting will silently hide real types.
  Prefer `mode: node` or `decay_factor: 0.3` instead.
- **Discovery / atlas-building runs** where the whole point is to find
  unexpected celltypes — restriction defeats the purpose.

## Validation

After setting `candidate_annotation`, re-run `run_pipeline.py` with
`--baseline <prev_outdir>` and check the autonomous signals again:

- **Signal C** (convergence to distant celltype) should drop to zero
  or near-zero.
- **Signal E** (init_weight top-1 ≠ path start) should drop sharply.
- **Accuracy** (if ground truth is available) should rise substantially
  on the cluster-level metric.

If the new run **regresses** vs baseline on any signal, the
candidate list is too narrow — expand it (add back celltypes that were
erroneously dropped) and re-run.
