# Data & Graph ID Namespace -- gap audit

The marker-->-homolog-->-celltype chain has **three string-ID matchings**
that must line up. Mismatch at any one step silently collapses the
result to zero KG hits and the post-run gate will then mark every cluster
as "not in KG". This document lists the expected ID format for every
species on every side of the chain, so the agent can detect a mismatch
**before** running BLASTP (which is the slow step that would otherwise
produce the bad output).

## The three IDs that must agree

```
adata.raw.var_names  ==  non_model_fasta header.id  ==  qseqid (BLAST)
                          (after hyphen->underscore)
                                                              ||
                                                              \/
                                          sseqid (BLAST db)  ==  KG Gene.Name
```

Read top-to-bottom:

1. **Step 1 (DEGs):** marker names come from `adata.raw.var_names`
   (if `adata.raw` exists and is sparse) -- see
   `references/log-interpretation.md` -> "Stage 2: get_markers" for
   the full `use_raw` decision rule. If `adata.raw` is **not** set or is
   dense, markers come from `adata.var_names` (the log-norm layer).
2. **Step 3 (BLAST):** `extract_fasta_by_name` matches each marker name
   against `record.id` in `non_model_fasta`, replacing `-` with `_` on
   both sides (`xener/utils/seq.py`). If your h5ad uses `LOC-Os01g01040`
   but your FASTA header is `LOC_Os01g01040`, the match still works
   (dash->underscore is normalized on both sides); the mismatch we care
   about is **a completely different ID scheme** (e.g. gene symbol vs.
   Ensembl).
3. **Step 5 (KG):** the BLAST `sseqid` becomes the KG query key. KG
   matches against `Gene.Name` (a cypher `MATCH (a:Gene)` with
   `a.Name IN {homolo_nodes}`), so `sseqid` must be **literally equal**
   to the KG node name -- there is no normalization, no alias lookup,
   no synonym table.

> **Why this matters.** A user with a `Homo_sapiens` h5ad whose
> `var_names` are HGNC symbols (`TP53`, `CD8A`) and whose
> `non_model_fasta` is the Ensembl proteome (headers `ENSG...`) will
> silently produce an empty BLAST result (the BLAST query FASTA is
> empty -- `extract_fasta_by_name` finds no header matching `TP53` in
> an Ensembl-headers FASTA). Conversely, a user with Ensembl-symbol
> `var_names` (`ENSG00000141510`) but the default `Homo_sapiens` model
> species (whose BLAST db uses HGNC symbols) gets a normal BLAST
> result, but **every homolog fails the KG lookup** -- verified
> empirically: `ENSG00000141510` -> 0 KG edges, `TP53` -> 27 KG edges.
> Both failure modes hit the same `>>>cell annotation` line in the log.

## Per-species ID reference

Empirically probed against `~/.xener/data/blastdb/prot/<Species>` via
`blastdbcmd -entry all -outfmt "%a"` (sseqid-only column), cross-checked
against the public cloud KG (`https://xenor.dcs.cloud`) with a
200-sseqid probe per species (`organ=Unknown`). Numbers below are
probed at skill-development time -- they shift with KG updates; for
fresh numbers run the probe in `scripts/probe_id_namespace.py` (if
installed) or the one-liner at the bottom of this file.

### Strong-coverage species (KG ↔ BLAST db agree; safe default `model_species`)

| `model_species` | BLAST db sseqid format | KG key = `Gene.Name` | Probe hit rate (200 sseqids, organ=Unknown) |
|---|---|---|---|
| `Arabidopsis_thaliana` | TAIR locus (`AT1G01010`, `AT3G24650`) | TAIR locus | 198/200 = 99% |
| `Oryza_sativa` | MSU v7 `LOC_Os\d{2}g\d{5}` | MSU `LOC_Os...` | 117/200 = 58% (KG subset; consider raising `top_num`) |
| `Homo_sapiens` | **HGNC symbols** (`TP53`, `CD8A`, `OR4F5`) -- *not* Ensembl | HGNC symbol | 189/200 = 95% |
| `Mus_musculus` | **MGI symbols** (`Xkr4`, `Sox17`, `Lypla1`) -- *not* Ensembl | MGI symbol | 113/200 = 57% (KG subset; `Trp53`/`Cd8a` etc. work; some symbols miss) |
| `Brassica_rapa` | `Bra\d{6}` (v3 ID) | `Bra...` | 110/200 = 55% |
| `Solanum_lycopersicum` | `Solyc\d{2}g\d{6}` (ITAG) | `Solyc...` | 19/200 = 10% -- see "BLAST-id-only species" below |
| `Glycine_max` | Wm82.a4 `Glyma.\d{2}G\d{6}` | `Glyma...` | 20/200 = 10% -- see "BLAST-id-only species" below |
| `Triticum_aestivum` | `TraesCS\d{1,2}[A-D]\d{2}G\d{6}` (IWGSC) | `TraesCS...` | 60/200 = 30% |
| `Manihot_esculenta` | `Manes.\d{2}G\d{6}` (v6) | `Manes...` | 124/200 = 62% |
| `Medicago_truncatula` | `MtrunA17Chr\d{1,2}g\d{7}` (Mt4.0) | `MtrunA17...` | 54/200 = 27% |
| `Fragaria_vesca` | `FvH4_\d{1,2}g\d{5}` (v4) | `FvH4...` | 93/200 = 47% |
| `Gossypium_hirsutum` | `Ghir_[A-D]\d{2}G\d{6}` (NBI) | `Ghir...` | 189/200 = 95% |
| `Nicotiana_tabacum` | `Nitab4\.5_\d{10}g\d{4}` | `Nitab4.5_...` | 3/200 = 1% (**very low** -- see "BLAST-id-only") |
| `Nicotiana_attenuata` | `A4A49_\d{5}` | `A4A49_...` | 149/200 = 75% |
| `Populus_alba_var_pyramidalis` | `pal_pou\d{5}` | `pal_...` | 152/200 = 76% |
| `Catharanthus_roseus` | `gene-M9H77_\d{5}` | `gene-M9H77_...` | 129/200 = 65% |
| `Bombax_ceiba` | `evm.model.Scaffold\d+.\d+` | `evm.model...` | 201/200 = 100% (sample size >200 due to dedup) |
| `Astyanax_mexicanus` | lowercase ZFIN symbol (`ptafr`, `hectd2`) | symbol (case may differ) | 1066/200 = high |
| `Danio_rerio` | lowercase ZFIN symbol (`si`, `guca1a`) | symbol (case may differ) | 753/200 = high |
| `Gasterosteus_aculeatus` | lowercase symbol (`ptgdsb.1`, `hacd2`) | symbol | 1476/200 = high |
| `Mastacembelus_armatus` | lowercase symbol (`lrrc69`, `slc16a4`) | symbol | 925/200 = high |
| `Monopterus_albus` | lowercase symbol (`nat8`, `cuedc2`) | symbol | 710/200 = high |
| `Nothobranchius_furzeri` | lowercase symbol (`lamtor5`, `tbc1d4`) | symbol | 826/200 = high |
| `Oncorhynchus_mykiss` | lowercase symbol (`kat14`, `b4galt3`) | symbol | 45/200 = 22% (**note: BLAST db has only ~hundreds of distinct sseqids** -- see "BLAST-db sparsity") |
| `Oreochromis_niloticus` | lowercase symbol (`brd7`, `luzp1`) | symbol | 890/200 = high |
| `Oryzias_latipes` | lowercase symbol (`gb`, `clec3b`) | symbol | 75/200 = 38% (**note: BLAST db has only ~hundreds of distinct sseqids**) |

### BLAST-id-only species (BLAST db present, but KG coverage is sparse)

These species have a working BLAST database but the KG only carries a
**small subset** of those IDs as `Gene.Name` nodes. Empirical probe
(`organ=Unknown`) confirms low hit rates:

| `model_species` | BLAST db sseqid format | Probe hit rate (200 sseqids) |
|---|---|---|
| `Zea_mays` | `Zm00001d\d{6}` (B73 v4/v5) | 56/200 = 28% (500 probe: 112/500 = 22%) |
| `Glycine_max` | Wm82.a4 `Glyma.\d{2}G\d{6}` | 20/200 = 10% (500 probe: 47/500 = 9%) |
| `Solanum_lycopersicum` | `Solyc\d{2}g\d{6}` (ITAG) | 19/200 = 10% |
| `Medicago_truncatula` | `MtrunA17Chr\d{1,2}g\d{7}` (Mt4.0) | 54/200 = 27% |
| `Nicotiana_tabacum` | `Nitab4\.5_\d{10}g\d{4}` | 3/200 = 1% |

What this means in practice:

- BLASTP runs and finds homologs normally.
- The homolog `sseqid` strings are valid (e.g. `Zm00001d035916`,
  `Glyma.01G132000`), but most of them do not exist as `Gene.Name`
  nodes in the current KG.
- Result: `total X% homolos of organ[...] not in kg` shows X>50%
  and the post-run gate emits `[WARN]` mean KG miss > 30%.
- **Fix as a soft lever** (do **not** change a HARD constraint):
  - Add a KG-richer `model_species` from the same family. For maize:
    `Oryza_sativa`, `Sorghum_bicolor` (not yet in bundled DB -- see
    `list_species.py`), or `Triticum_aestivum`. For soybean:
    `Medicago_truncatula`, or `Lotus_japonicus` (not yet in bundled
    DB) -- legumes share more gene-symbol conventions than the
    maize/grass clade. For tomato (`Solanum_lycopersicum`):
    `Nicotiana_tabacum` is also low -- try `Solanum_lycopersicum`
    plus a Solanaceae relative outside the bundled DB
    (`Solanum_tuberosum`, `Capsicum_annuum`), or accept the
    sparseness. For tobacco (`Nicotiana_tabacum`):
    `Nicotiana_attenuata` (75% hit rate) is the bundled rescue
    option.
  - Raise `top_num` to 50+ so the per-cluster candidate set is larger
    and you do not lose all coverage to a thin homolo pool.
  - If the user's biological question is anchored on one of these
    species specifically (i.e. that one species must remain in
    `model_species`), keep it and **accept** the higher miss rate
    -- never drop the species to game the gate
    (`mandatory-rules.md` Sec. 11).

### Species present in KG but missing from bundled BLAST db

The public KG also lists the following species that are **not** in the
bundled BLAST database -- `list_species.py` filters to the BLAST
directory, so they will not appear there:

- `gossypium_bickii`
- `populus_alba_x_populus_glandulosa`

If your target is one of these, you cannot run a default cross-species
annotation against it: BLASTP will fail with `BLAST db <X> not found`.
The supported path is the custom `--init-config` workflow
(`references/workflows/initialization.md`) with a locally-built BLAST
DB -- out of scope for the bundled skill.

### Species present in BLAST db but absent from KG

- `Bombax_ceiba` (BLAST db present, no KG species row)

Markers from a Bombax query will produce BLAST hits, but those `sseqid`
strings (`evm.model.Scaffold...`) are not in the KG. Annotation will
collapse to "not in KG" for every cluster. Use only as a homology
reference, not as a primary `model_species` for cell-type lookup.

## Common ID-mismatch pitfalls (and how to detect them)

### Section 1. Human/mouse data with Ensembl `var_names` (`ENSG...`, `ENSMUSG...`)

This is the most common case in published scRNA-seq datasets (CellxGene,
Tabula Sapiens, etc.). The bundled BLAST db uses HGNC / MGI symbols.

| Symptom | Detection | Fix |
|---|---|---|
| `extract_fasta_by_name` reports `Extracted 0/N sequences from ...` | inspect log: `Extracted 0/...` | Switch `non_model_fasta` to a protein FASTA whose headers are HGNC / MGI symbols (e.g. download from HGNC/MGI), **OR** map your `var_names` from Ensembl -> symbol before running |
| BLAST succeeds but `>>>cell annotation` shows `total 100% homolos ... not in kg` | log landmark `hmolo[X] of organ[Y] not in kg` | The BLAST sseqids are HGNC symbols, but the `homolo` is fine. The miss rate comes from a different cause (KG has no edge for the organ you picked). Re-check the organ field first. |

**Detection rule for the agent:** if `inspect_h5ad.py` reports
`var_names_sample` starting with `ENSG\d+` or `ENSMUSG\d+` for a
human/mouse target, **stop and warn the user** before running:

> *"Inspection identifies this as `Homo_sapiens` data with Ensembl
> gene IDs (`ENSG00000141510` etc.). The bundled `Homo_sapiens` BLAST
> database is keyed on HGNC symbols (`TP53`, etc.), so direct
> `extract_fasta_by_name` will find 0 / N markers and the BLAST query
> FASTA will be empty. You have three options:*
> 1. *Provide an HGNC-symbol protein FASTA as `non_model_fasta`
>    (e.g. download from HGNC),*
> 2. *Map your `var_names` from Ensembl -> HGNC symbol in a
>    preprocessing step (out of scope for the skill),*
> 3. *Convert your `var_names` to symbols and re-save the h5ad with
>    `adata.raw.var_names = symbols`, then re-run.*
> *Default: option 1 (HGNC protein FASTA). Confirm before running."*

### Section 2. Plant data with mixed gene-model versions

Different community releases of the same species use different
identifier conventions. The most common offenders:

- **Maize**: `Zm00001d...` (B73 v4/v5, NCBI RefSeq) vs. `GRMZM...`
  (B73 v3 / MaizeGDB / older community). BLAST db is v4/v5; KG is
  mostly empty (see above) -- both versions miss most of the time.
  If your `var_names` are `GRMZM...`, you need a `GRMZM` header
  FASTA and the BLAST hit count will be tiny. Best mitigation: add
  `Oryza_sativa` or `Sorghum_bicolor` to `model_species`.
- **Rice**: `LOC_Os...` (MSU/RAP-DB) vs. `Os\d+g...` (some
  annotation pipelines). BLAST db uses MSU. If your data uses RAP
  IDs without the `LOC_` prefix, BLAST hits will still work via
  blastp (BLAST is sequence-based, not name-based) but the `homolo`
  column will be a MSU ID -- verify the KG has `LOC_Os...` entries
  (yes, it does; see table above).
- **Soybean**: `Glyma.\d{2}G\d{6}` (Wm82.a4/v4, BLAST db) vs.
  `Glyma\d{2}G\d{6}` (older Wm82.a2). BLAST db uses v4. KG
  coverage is sparse for both.
- **Wheat**: IWGSC `TraesCS...` vs. Chinese Spring `TGACv1`. BLAST
  db uses IWGSC.

Detection: if `inspect_h5ad.py` reports `var_names` with a prefix
not in the `SPECIES_HINTS` table (or in the per-species table
above), warn the user that the BLAST DB may not be keyed to their
gene-model release.

### Section 3. Self-annotation shortcut (`skip_blast: true`) requires an exact ID match

When `skip_blast: true` is set, the marker gene IDs go **directly to
the KG** (no BLAST in between). The ID namespace is therefore
**`adata.raw.var_names == KG Gene.Name`** with zero tolerance.

- ✅ `var_names` are TAIR loci + `model_species: [Arabidopsis_thaliana]`
- ❌ `var_names` are Ensembl + `model_species: [Homo_sapiens]`
- ❌ `var_names` are `Zm00001d...` + `model_species: [Zea_mays]` (KG is sparse)

The shortcut is only safe when your data and the bundled KG use the
**same identifier scheme**. Verify by inspecting `var_names_sample`
in the inspect output and cross-referencing the table above. The
post-run gate's `mean KG miss` is the authoritative test -- if
`skip_blast: true` is set on mismatched IDs, expect `mean KG miss`
near 100% and most clusters will be unannotated.

### Section 4. Dense `adata.raw` (the silent use_raw=False case)

The DEG step uses `adata.raw` only when `adata.raw.X` is **sparse**
(`xener/core.py::get_markers`):

```python
raw_available = hasattr(adata, 'raw') and adata.raw is not None
use_raw = raw_available and issparse(adata.raw.X)
```

If your h5ad was saved with a dense `adata.raw` (older scanpy
versions, or someone explicitly densified it), `use_raw` is `False`
and markers come from `adata.var_names` instead. If your `.raw`
and `.X` layers have **different** `var_names` (rare, but happens
when `raw` was saved before gene filtering and `.X` after), you get
a mix that the pipeline does not detect.

Detection: inspect log line `use_raw[False]` when you expected
`use_raw[True]`. The fix is to re-save the h5ad with sparse
`raw`: `adata.raw = ad.AnnData(X=sc.sparse.csr_matrix(adata.raw.X),
var=adata.raw.var)`.

### Section 5. Non-model target with no close `model_species`

If the target is bamboo, salmon, octopus, etc., the closest
`model_species` may be quite distant (different genus/family).
BLASTP will still find homologs, but the BLAST sseqid will be from
the chosen `model_species`'s ID namespace -- which the user may
not have realized. Cross-species transfer is allowed (`AGENTS.md`
quality gate section), but the user should know that the resulting
`homolo` strings belong to the *reference* species, not the target.
This is not a bug, just a documentation gap.

## How the agent should validate BEFORE running

After `inspect_h5ad.py` reports `var_names_sample` and a
`species_hint`, the agent should run a single **preflight check**
before composing the final config. Add this block to the inspect
report (planned future feature in `scripts/inspect_h5ad.py` --
for now do it inline, using the table above as ground truth):

```text
var_names_sample[:5] = [...]
species_hint = <X>
self_annotation? <yes/no>
  if yes: var_names prefix in {AT, LOC_Os, ENSG, ENSMUSG, HGNC-symbol, MGI-symbol}?
    and KG Gene.Name uses the SAME namespace? -> safe to set skip_blast: true
  if no: model_species contains target clade? -> ok
    and non_model_fasta headers match var_names? -> ok (otherwise step 3 BLAST is empty)
```

If any of those checks fails, **stop and ask the user** before
running -- the failure mode is silent (zero KG hits) and only the
post-run gate's `[WARN]` will catch it, after a multi-minute BLAST
waste.

## Empirical probe (one-liner)

To re-measure the per-species hit rate at any time (output to a
file because Windows console encoding will mangle stdout):

```bash
python -c "
import sys, subprocess
sys.path.insert(0, 'skill/xener/scripts')
from _xener_init import build_xener
annor, _ = build_xener()
BD = r'C:\Program Files\NCBI\blast-2.17.0+\bin\blastdbcmd.exe'
for sp in sorted(['Arabidopsis_thaliana','Oryza_sativa','Homo_sapiens','Mus_musculus','Zea_mays','Glycine_max']):
    out = subprocess.check_output([BD,'-db',rf'C:\Users\kip\.xener\data\blastdb\prot\{sp}','-entry','all','-outfmt','%a'],stderr=subprocess.DEVNULL).decode().splitlines()
    sample = list(dict.fromkeys(out))[:500]
    g,c,m = annor.KG.get_gene2celltype_kg(sample, organ='Unknown')
    hit = sum(1 for r in m if r.nnz>0)
    print(f'{sp:25s} sample={len(sample):4d} matched={hit:4d} nnz={m.nnz}')
annor.close()
" > probe.txt 2>&1
```

Adjust the `BD` and DB paths for your platform. Replace `Homo_sapiens`
with whatever species is on your machine.
