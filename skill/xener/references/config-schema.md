# Config Schema (YAML)

A complete reference for the YAML configuration file passed to
`scripts/run_pipeline.py --config <path>`.

## Full example

```yaml
# Required fields
cluster_key: leiden
model_species:
  - Brassica_rapa
non_model_h5ad: ERP132245.h5ad
organ: leaf
outdir: output/ERP132245
# non_model_fasta is REQUIRED when skip_blast is unset/false — drop it only when skip_blast: true
non_model_fasta: Arabidopsis_thaliana.fasta

# Optional fields (defaults shown)
marker_weight_method: prod          # prod | sum
top_num: 30                         # Top N genes per cluster
homolo_weight_key: pident           # pident | evalue | bitscore
multihomolo: true                   # Keep multiple homologs per gene
decay_factor: 0.7                   # Weight decay for graph propagation
mode: path                          # node | path
threshold: null                     # Z-score threshold for filtering
mapping_strict: 0                   # -1=loose, 0=default, 1=per-group max
ann_strict: 0                       # <0=binarize, 0=default, 1=per-row max, 2=global max
skip_blast: false                   # true: skip BLAST, use marker gene IDs as KG keys directly
candidate_annotation:               # Restrict cell types (optional)
  - type1
  - type2
```

## Field reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cluster_key` | string | yes | — | Column in `adata.obs` containing cluster labels |
| `model_species` | list[string] | yes | — | One or more model species for BLAST. Must appear in `list_species.py` output |
| `non_model_fasta` | string \| null | conditional | — | Path to FASTA file of the non-model species. **Required when `skip_blast: false`** (the default). May be omitted when `skip_blast: true` — step 3 then bypasses BLAST and the marker's gene IDs become KG keys directly. |
| `non_model_h5ad` | string | yes | — | Path to h5ad file of the non-model species |
| `organ` | string | yes | — | Organ filter for the knowledge graph. Must appear in `list_organs.py` output |
| `outdir` | string | yes | — | Output directory (created if missing) |
| `marker_weight_method` | string | no | `prod` | How to combine marker scores: `prod` (product) or `sum` (sum) |
| `top_num` | int | no | `30` | Top N genes retained per cluster after step 4 |
| `homolo_weight_key` | string | no | `pident` | Which BLAST column to use as the homology weight |
| `multihomolo` | bool | no | `true` | If `true`, keep multiple homologs per non-model gene |
| `decay_factor` | float | no | `0.7` | Graph weight decay at each propagation hop |
| `mode` | string | no | `path` | `node` (single type) or `path` (trajectory-aware) |
| `threshold` | float \| null | no | `null` | Z-score threshold for filtering low-weight cell types |
| `mapping_strict` | int | no | `0` | Strict mode for BLAST mapping: <0=loose (weight=1), 0=default, 1=per-group max |
| `ann_strict` | int | no | `0` | Strict mode for annotation: <0=binarize, 0=default, 1=per-row max, 2=global max |
| `candidate_annotation` | list[string] | no | `null` | Restrict the output cell-type set |
| `skip_blast` | bool | no | `false` | Skip BLASTP (step 3) and use marker gene IDs directly as the KG homology key (`homolo == gene`). Requires `len(model_species) == 1`. Intended for annotating a model species against itself; see `references/workflows/species-selection.md` → "Self-annotation shortcut (skip_blast)" for the four-species table (`Arabidopsis_thaliana`, `Oryza_sativa`, `Homo_sapiens`, `Mus_musculus`) and the auto-detection rule. |

## Minimal example

If you do not need to override any defaults:

```yaml
cluster_key: leiden
model_species:
  - Brassica_rapa
non_model_fasta: Arabidopsis_thaliana.fasta
non_model_h5ad: ERP132245.h5ad
organ: leaf
outdir: output/ERP132245
```

## Naming convention for `outdir`

Recommended: include the dataset label in the path (e.g.,
`output/PRJNA662627/`) so multiple runs do not collide.

## Optional: init-config keys (WHERE Xener gets its data)

The fields above are the **run config** — they say *what* to annotate. A
separate, optional set of keys controls *where* Xener gets its data: which
Knowledge Graph to connect to and which BLAST database to use. With none of
them, Xener uses the public cloud KG (`https://xenor.dcs.cloud`) and the
bundled BLAST database — the default for virtually every run.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `KG_url` | string | cloud | KG endpoint. `http(s)://` → HTTP backend; `bolt://` → Neo4j Bolt backend |
| `KG_usr` | string | none | KG username (Bolt backend) |
| `KG_pwd` | string | none | KG password (Bolt backend) |
| `blastdb_path` | string | bundled | Local BLAST protein DB directory (makeblastdb output) |
| `blastp_result_path` | string | none | Optional BLASTP result cache directory |
| `blastp_path` | string | system PATH | Path to the `blastp` executable (or to the directory that contains it, e.g. a conda env's `bin/`). Use when `blastp` is not on `$PATH` or you need a specific version. |

These can be supplied either as a **separate** `--init-config` YAML or
**inlined** into this config file (a separate file wins if both are present).
Validate them with `python scripts/init_xener.py --init-config <file>` before
running. Full guidance and examples: `workflows/initialization.md` and
`examples/xener-init.example.yaml`.

