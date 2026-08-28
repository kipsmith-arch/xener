# h5ad Inspection Workflow

Before running the pipeline, the agent **must inspect the h5ad file**
to extract metadata and make informed parameter decisions. This file
documents the inspection procedure.

## Why inspect first?

- The agent needs `cluster_key` -- usually stored in `adata.obs`
- The agent may need species hints (var name prefix, uns metadata)
- The agent may need organ hints (uns metadata, file path)
- The agent needs to estimate `top_num` based on cluster sizes

## Inspect with `scripts/inspect_h5ad.py` (load the h5ad ONCE)

Run the dedicated inspection script. It loads the (often multi-GB) h5ad
**exactly once** and prints every field you need to compose a config:

```bash
python scripts/inspect_h5ad.py --input <path_to_h5ad>
python scripts/inspect_h5ad.py --input <path_to_h5ad> --json   # machine-readable
```

It reports: shape; obs columns + cardinality; **recommended `cluster_key`**
(leiden -> louvain -> *cluster*, skipping existing `celltype`/`annotation`
columns); `uns` keys; `var_names` sample **+ detected species**; `obsm` keys
(is `X_umap` present?); whether `raw` is set; an `.X` sparsity/range/log-norm
sanity check; **cluster-size summary** (n / min / median / mean / max) for the
recommended key; a **recommended `top_num`**; and **organ/tissue hints**.

> **Do NOT follow this with ad-hoc `python -c "import scanpy; sc.read(...)"`
> reads to grab "one more field".** Every field needed to write the config is
> already in the output above. Each extra read of a ~1 GB h5ad is ~30-45 s and
> is the single largest I/O cost of the workflow. This is the I/O discipline
> mandated by `mandatory-rules.md` Sec. 10. (`inspect_h5ad.py` imports `scanpy`
> directly; this is the sanctioned inspection path, alongside the rule Sec. 1
> exception. It never `import xener` and needs no `--init-config`.)

The decision tables below explain how to *interpret* the script's output.

## Decision rules

### cluster_key

Pick the first column with cardinality 5-50 (typical clustering range):

| Column name contains | Priority |
|---------------------|----------|
| `leiden`, `louvain` | High |
| `celltype`, `annotation` (existing) | Skip (don't re-annotate) |
| `cluster`, `cluster_id` | Medium |
| Numeric only (e.g., `X_kmeans`) | Low |

**Fallback**: if no clustering column exists, default `cluster_key: leiden`
(see the auto-leiden path below). The agent should **not** stop to ask
the user which clustering algorithm to use; `leiden` with default
resolution is the standard default and the Xener pipeline will run it
on demand. (Genepilote rollout decision: "no need to ask the user for
this choice.")

#### What if there is no cluster_key in `adata.obs`? (auto-leiden path -- DEFAULT)

`inspect_h5ad.py` reports `recommended cluster_key: None (-1 clusters)`
when no `leiden`/`louvain`/`*cluster*` column is found. **This is the
default case for raw single-cell h5ads that have not been pre-clustered
upstream, and the agent MUST handle it without asking the user.** The
Xener pipeline supports the value `cluster_key: leiden` even when
`adata.obs['leiden']` does not exist yet -- xener's internal `process()`
function runs `PCA -> neighbors -> leiden -> UMAP` on the `.X` layer on
demand and writes the resulting labels back to `adata.obs['leiden']`
before `rank_genes_groups` (see `xener/utils/h5ad/preprocess.py::process`).

Concretely, the default config when the h5ad has no precomputed
clustering is:

```yaml
cluster_key: leiden         # default when no cluster column exists
model_species: [Homo_sapiens]
non_model_h5ad: data.h5ad
organ: Unknown               # or whatever list_organs.py accepts
outdir: output/dataset
skip_blast: true             # if the target IS one of the 4 model species
```

Trade-offs of the auto-leiden path:

- **Pros**: zero preprocessing script to write or maintain; respects
  mandatory-rules Sec. 4 (no new scripts); xener also writes the resulting
  `X_umap` so `plot_umap.py --mode overview` works out of the box.
- **Cons**: xener uses the `leidenalg` flavor with default resolution
  (1.0) and default PCA dimensionality from `sc.pp.pca` (50 PCs). If you
  need a specific resolution (e.g. coarser clusters for a small dataset),
  you must either precompute a clustering column with scanpy yourself, or
  edit `xener/utils/h5ad/preprocess.py::process` (out of scope for the
  agent skill).

`step1_markers.py` and `run_pipeline.py` both detect the
`cluster_key='leiden'` + missing-`leiden`-column case and emit a one-line
`[INFO]` notice before the auto-cluster step starts, so the I/O + leiden
cost (typically 1-3 minutes on a 15-25k-cell dataset) is not silent.

Do NOT write a separate preprocessing script just to add a `leiden`
column -- `mandatory-rules.md` Sec. 4 forbids new scripts, and the
auto-leiden path is already wired up.

### Species hint detection

| Signal | Detected species |
|--------|------------------|
| var_names start with `AT` or `AT[0-9]G` (TAIR locus IDs) | Arabidopsis_thaliana |
| var_names start with `Zm` or `Zm00001` | Zea_mays |
| var_names start with `Os` or `LOC_Os` | Oryza_sativa |
| var_names start with `Brara\|Bra` | Brassica_rapa |
| var_names contain `Medtr\|MTR_` | Medicago_truncatula |
| var_names contain `Glyma\.` | Glycine_max |
| var_names match `^ENSG\d+(\.\d+)?$` (Ensembl human gene IDs) | Homo_sapiens |
| var_names match `^ENSMUSG\d+(\.\d+)?$` (Ensembl mouse gene IDs) | Mus_musculus |
| HGNC symbols (e.g. `TP53`, `CD8A`) at high coverage in var_names | Homo_sapiens |
| MGI symbols (e.g. `Trp53`, `Cd8a`) at high coverage in var_names | Mus_musculus |
| `adata.uns['organism']` set | Use that value directly (canonicalize to a xener species name) |
| `adata.uns['species']` set | Use that value directly |

> **Note on Ensembl / MGI / HGNC prefixes:** the inspect script's
> `detect_species` covers the plant prefixes above (see
> `scripts/inspect_h5ad.py` -> `SPECIES_HINTS`). It does **not** yet have
> regex entries for `ENSG` / `ENSMUSG`; for human/mouse data the agent
> should additionally read `uns['organism']` from the inspect output
> (or do a lightweight regex check on a sample of `var_names`).
> Either path satisfies one of the two-signal rule in
> `species-selection.md` -> "Self-annotation shortcut".

If detected, look up in `species-selection.md` and propose 1-3
model_species. **Always confirm with user** before running. If the
detected species is one of the four in the
[self-annotation shortcut table](species-selection.md#self-annotation-shortcut-skip_blast)
(Arabidopsis / Oryza / human / mouse), consider applying that shortcut.

### **Mandatory: ID-namespace preflight (read `data-id-namespace.md` first)**

The marker-->-BLAST-->-KG chain requires three string IDs to line up:

```
adata.raw.var_names  ==  non_model_fasta header.id  ==  KG Gene.Name
```

A mismatch at any step silently collapses the run to zero KG hits.
After `inspect_h5ad.py` reports `var_names_sample[:10]` and
`species_hint`, the agent MUST run this preflight before composing
`config.yaml`:

1. **Confirm var_names are the right kind for the chosen
   `model_species`.** Full per-species table is in
   [`data-id-namespace.md`](../data-id-namespace.md). The four
   high-coverage self-annotation shortcuts are:
   - `Arabidopsis_thaliana` ↔ TAIR locus (`AT\dG\d{5}`)
   - `Oryza_sativa` ↔ MSU `LOC_Os\d{2}g\d{5}`
   - `Homo_sapiens` ↔ **HGNC symbols** (`TP53`, `CD8A`), NOT Ensembl
   - `Mus_musculus` -> **MGI symbols** (`Trp53`, `Cd8a`), NOT Ensembl
   If `var_names` are Ensembl IDs (`ENSG...` / `ENSMUSG...`) for
   human/mouse targets, the bundled BLAST db is keyed on
   symbols -- `extract_fasta_by_name` will find **0 / N markers** and
   the BLAST query FASTA will be empty. **Stop and warn the user**
   before running; see `data-id-namespace.md` Sec. 1 for the three
   fix options.
2. **Confirm `non_model_fasta` headers match `var_names`.** If your
   h5ad uses Ensembl IDs but the FASTA uses HGNC symbols, BLAST
   finds nothing. The pipeline logs `Extracted 0/N sequences from
   <fasta>` -- look for it.
3. **If planning `skip_blast: true`:** the ID namespace is
   `adata.raw.var_names == KG Gene.Name` with zero tolerance. The
   shortcut is only safe when both sides use the same identifier
   scheme. `Zea_mays` and `Glycine_max` are **not** safe for
   `skip_blast: true` -- the KG is sparsely populated even for
   their canonical BLAST-db IDs (see `data-id-namespace.md` ->
   "BLAST-id-only species").
4. **If `adata.raw` is dense (`X_check` reports sparse=False and
   you expected `use_raw[True]`):** the pipeline falls back to
   `adata.var_names`. If your `.raw` and `.X` have different
   `var_names` (e.g. raw was saved before gene filtering), markers
   come from `.X` instead -- and that may not match either your
   FASTA or the KG. Re-save with sparse raw
   (`adata.raw = ad.AnnData(X=scipy.sparse.csr_matrix(adata.raw.X),
   var=adata.raw.var)`) and re-run.

The full per-species reference, common-mismatch table, and a
self-probe one-liner live in
[`data-id-namespace.md`](../data-id-namespace.md). Load it
**before** composing `config.yaml` -- not after the post-run
gate flags the failure.

### Organ hint detection

| Signal | Detected organ |
|--------|----------------|
| h5ad path contains `leaf` | leaf |
| h5ad path contains `root` | root |
| `adata.uns['tissue']` or `adata.uns['organ']` set | Use that value |
| User prompt mentions tissue name | Match against `list_organs.py` output |
| Nothing detected | Default to the most common organ in the dataset, or ask |

### Cluster size for top_num estimation

Compute median cluster size `N_med`. Then:

```text
if N_med < 50:   top_num = 50
elif N_med < 200: top_num = 30   (default)
elif N_med < 1000: top_num = 20
else:            top_num = 15
```

Rationale: smaller clusters need more candidate genes to find
specific markers; larger clusters have abundant signal and can
afford smaller top_num.

## What to do with the inspection result

1. **Compose a config.yaml** with the inferred values (the script already
   recommends `cluster_key` and `top_num`; you decide `model_species` and
   `organ` from the species/organ hints).
2. **Present it to the user** with reasoning for each non-trivial choice
   (species, organ) -- unless the user has asked you to run fully autonomously,
   in which case log the reasoning instead of blocking on confirmation.
3. **For technical parameters** (top_num, mode, decay_factor, etc.),
   just include them in the config with a brief inline comment.
4. **Do not re-read the h5ad.** Everything you need is in the
   `inspect_h5ad.py` output; a second `sc.read()` of a multi-GB file is the
   most common avoidable I/O cost (`mandatory-rules.md` Sec. 10).

Example presentation:

```
I inspected the h5ad file (one load, scripts/inspect_h5ad.py) and detected:
- cluster_key: "leiden" (15 clusters)
- species hint: var_names start with "Zm" -> Zea_mays (maize)
- organ: not detected in metadata
- recommended top_num: 30 (median cluster size = 180 cells)

Proposed config:
- model_species: [Zea_mays, Oryza_sativa, Sorghum_bicolor]
  (same family Poaceae, all 3 have gene models in xener)
- organ: leaf (default; please confirm)
- top_num: 30
```
