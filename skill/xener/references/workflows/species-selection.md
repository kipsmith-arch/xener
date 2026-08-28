# Species Selection Heuristics

The agent should select `model_species` automatically based on the
target (non-model) species. This document provides the decision
heuristic.

## Quick algorithm

```text
1. Detect target species from:
   - h5ad var_names prefix (e.g., "AT" -> Arabidopsis, "Zm" -> maize)
   - h5ad uns['organism'] or similar metadata
   - filename hints
   - user prompt keywords

2. If detected, pick 1-3 species from the SAME taxonomic family (preferred):
   - Phylogenetic distance: same genus > same family > same order
   - Trade-off: more species = more homolog evidence, but more noise

3. If not detected, list available species to the user and ask
   for the target species first.

4. `model_species` is a SOFT lever, not a hard boundary. The family
   preference in step 2 is exactly that -- a preference. When the close
   relatives are absent from the KG, or present but shallow for the target
   organ (e.g. the post-run gate reports a high KG-miss), you MAY supplement
   the list with more distant species that are well-represented in the KG.
   Keep the close relatives in the list, prefer the closest species that has
   sufficient KG depth, and treat distant additions as KG-coverage rescue --
   distant homology transfers less reliably, so it is a supplement, not a
   replacement. The only hard fact about a species is that it must exist in
   the KG + BLAST DB. See `mandatory-rules.md` Sec. 11.
```

## Phylogenetic distance table (plants)

Use this table to map target species -> recommended model species.

| Target family / species | Recommended model_species |
|-------------------------|---------------------------|
| Brassicaceae (Brassica, Arabidopsis) | Arabidopsis_thaliana, Brassica_rapa |
| Poaceae / grasses (rice, wheat, maize, bamboo) | Oryza_sativa, Zea_mays, Triticum_aestivum, Sorghum_bicolor |
| Fabaceae / legumes (soybean, Medicago, pea) | Glycine_max, Medicago_truncatula, Lotus_japonicus |
| Solanaceae (tomato, tobacco, potato) | Solanum_lycopersicum, Nicotiana_tabacum |
| Asteraceae (sunflower, lettuce) | Helianthus_annuus, Lactuca_sativa |
| Rosaceae (apple, strawberry, peach) | Fragaria_vesca, Prunus_persica, Malus_domestica |
| Cucurbitaceae (cucumber, melon) | Cucumis_sativus, Cucumis_melo |
| Malvaceae (cotton) | Gossypium_hirsutum |
| Vitaceae (grape) | Vitis_vinifera |
| Salicaceae (poplar) | Populus_trichocarpa |
| Others / unknown | Ask the user, or use Arabidopsis_thaliana + Oryza_sativa as a safe cross-kingdom pair |

## Phylogenetic distance table (animals)

| Target | Recommended model_species |
|--------|---------------------------|
| Primates | Homo_sapiens, Macaca_mulatta |
| Rodents | Mus_musculus, Rattus_norvegicus |
| Other mammals | Homo_sapiens, Mus_musculus |
| Zebrafish / fish | Danio_rerio |
| Chicken | Gallus_gallus |
| Drosophila | Drosophila_melanogaster |
| C. elegans | Caenorhabditis_elegans |

### Default `organ` for animal datasets (no KG-matched organ)

The bundled Knowledge Graph currently exposes **plant** organ taxonomy only
(`list_organs.py` returns Flower / Fruit / Leaf / Root / Seed / Stem plus
`` and `Unknown`). Animal cell atlases (human, mouse, zebrafish, etc.)
have **no anatomically matching `organ` value** in the KG. When the
target is an animal species:

1. **Default `organ: Unknown`** -- `Unknown` is a literal value accepted
   by `list_organs.py`. Setting it disables the organ filter on the KG
   side, so all cell-type edges (regardless of the upstream source
   organ) are eligible. This is the **default for every animal
   dataset** unless the user explicitly names a different organ value.
2. **Never invent a plant organ** (Leaf / Root / etc.) for an animal
   sample just because the KG list happens to be plant-only. Switching
   `organ` to a plant value the tissue is not would falsify a HARD
   constraint (`mandatory-rules.md` Sec. 11) for the sole purpose of
   passing the quality gate.
3. **Cross-kingdom annotation is allowed** -- e.g. annotating a plant
   sample against a fish or human `model_species` to rescue KG
   coverage is a soft lever; the species just has to exist in
   `list_species.py`. The reverse (animal target, plant `organ`) is
   the only direction that is not legal by default.

Detection rule:

- If `species_hint` / `uns['organism']` / var_names regex classify the
  target as an animal (any of `Homo_sapiens`, `Mus_musculus`,
  `Rattus_norvegicus`, `Danio_rerio`, `Gallus_gallus`,
  `Drosophila_melanogaster`, `Caenorhabditis_elegans`, `Macaca_mulatta`,
  or a regex match on `ENSG\d+` / `ENSMUSG\d+` / known MGI symbols),
  set `organ: Unknown` by default and tell the user in plain
  language: *"Inspection identifies this dataset as an animal atlas
  (Homo_sapiens). The bundled KG only has plant organ taxonomy; using
  `organ: Unknown` to disable the organ filter. Override this if you
  have a specific organ you want to filter on."*
- Plant targets keep the standard confirmation per Sec. 3 of
  `mandatory-rules.md` (propose 1-3 candidates from the plant organ
  table above, wait for yes/override).

This rule supersedes the general "always confirm `organ` with the user"
default for the animal case only -- the user's later request from this
genepilote roll-out was: *"图谱中的动物都没有明确 organ"*, i.e. do not
block on a confirmation question when the dataset is clearly an animal
and the KG cannot answer the organ question anyway.

## BLAST threshold guidance by distance

Adjust `--pident` and `--evalue` based on phylogenetic distance:

| Distance | --pident | --evalue | --bitscore |
|----------|----------|----------|------------|
| Same genus | 80 | 0.01 | 300 |
| Same family | 60 | 0.05 | 200 (default) |
| Same order | 45 | 0.1 | 150 |
| Same kingdom (distant) | 30 | 1.0 | 100 |

## Multiple model_species strategy

For non-model species without close relatives, using 2-3 distantly
related model species can rescue weak annotations:

```bash
python scripts/step3_mapping.py \
    --input output/marker_weight.csv \
    --fasta target.fasta \
    --species Oryza_sativa Arabidopsis_thaliana Zea_mays \
    --pident 40 --evalue 0.1 --bitscore 150 \
    --outdir output/
```

The pipeline automatically merges homologs from multiple species.
This is **strongly recommended** for novel species with no close
reference genome.

## Always-validate step

After picking candidates, **always run**:

```bash
python scripts/list_species.py
```

and verify each candidate appears in the output before using it in
the config. Cross-reference with `references/config-schema.md` for
the exact field format.

## Worked example: target IS a model species

**Common pitfall:** the target species is already a well-annotated
model organism (e.g., the user has an Arabidopsis h5ad and treats it as
`non_model_h5ad`). The agent may wrongly exclude the target species
from `model_species` thinking "self-mapping defeats the purpose".

**Correct decision:** include the target species in `model_species`
together with 1-2 close relatives. The xener KG has the deepest
gene->celltype edges for model organisms; self-mapping gives the highest
KG hit rate. Cross-species independence is served by adding the
relatives, not by excluding self.

Concrete config for an Arabidopsis root dataset:

```yaml
cluster_key: leiden
model_species:
  - Arabidopsis_thaliana   # target species itself - highest KG coverage
  - Brassica_rapa          # close relative - independent corroboration
non_model_fasta: abc.fasta
non_model_h5ad: edf.h5ad
organ: Root
outdir: output/edf
```

Excluding `Arabidopsis_thaliana` here typically produces 30-75% of
homologs "not in KG" and reduces the observed cell-type diversity by
half or more. The `scripts/check_output.py` post-run gate will catch
this.

### Self-annotation shortcut (skip_blast)

When the target species is itself a well-curated model organism whose
gene IDs already match a xener reference, BLASTP is pure overhead --
there are no homologs to find; the marker gene IDs already ARE the KG
keys. Set `skip_blast: true` and (optionally) drop `non_model_fasta`
entirely. The behavior is:

- Step 3 writes `gene_homolo_weight.csv` with `homolo == gene` and
  `homolo_weight == 1` (identity mapping); no BLASTP is launched.
- `len(model_species) != 1` is rejected (multi-species merging is the
  whole reason BLASTP exists).
- `mapping_strict` is ignored; non-zero values log a warning.
- `non_model_fasta` is **optional** in this mode; if present it is read
  but never used (a one-line warning is logged).

The skill maintains a fixed list of **four** species whose gene-ID
namespace is exactly the xener KG namespace, and for which
self-annotation is a safe, high-coverage default:

| Canonical `model_species` value | Detection signals the agent should look for |
|---|---|
| `Arabidopsis_thaliana` | var_names match `^AT[1-5]G\d{5}$` (TAIR locus IDs); `uns['organism']` contains `Arabidopsis` / `thaliana`; file path keyword `arabidopsis`/`at` |
| `Oryza_sativa` | var_names match `^LOC_Os\d+g\d+(\.\d+)?$` or start with `Os`+digit/`Os0`/`Os1`...; `uns['organism']` contains `Oryza` / `sativa` / `rice`; file path keyword `rice`/`oryza` |
| `Homo_sapiens` | var_names are HGNC symbols (e.g. `TP53`, `CD8A`) at high coverage; `uns['organism']` contains `Homo` / `sapiens` / `human`; file path keyword `human`/`homo`. **Note:** if var_names are Ensembl IDs (`ENSG\d+`), the bundled BLAST db cannot be used without an HGNC-symbol FASTA -- see `data-id-namespace.md` Sec. 1. |
| `Mus_musculus` | var_names are MGI symbols (e.g. `Trp53`, `Cd8a`) at high coverage; `uns['organism']` contains `Mus` / `musculus` / `mouse`. **Note:** if var_names are Ensembl IDs (`ENSMUSG\d+`), see `data-id-namespace.md` Sec. 1. |

**Detection rule for the agent.** Treat the input as a "self-annotation
candidate" only if **at least two independent signals agree**:

1. `scripts/inspect_h5ad.py` reports a `species_hint` of one of the four
   values (currently covers `Arabidopsis_thaliana` / `Oryza_sativa` via
   var_names prefix -- see `inspection.md`), OR
2. `adata.uns['organism']` / `uns['species']` matches one of the four
   (read from the inspect script's `organ_hints` block), OR
3. var_names match one of the regexes above with >=50% coverage.

A single weak signal (e.g. only the file path) is not enough -- ask the
user. Two or more signals that agree -> set `model_species: [<that one>]`
and `skip_blast: true`, and **tell the user** in plain language:
*"Inspection identifies this dataset as Homo_sapiens (var_names are Ensembl
gene IDs and uns['organism']='Homo sapiens'). Setting
`model_species: [Homo_sapiens]` and `skip_blast: true` for a pure
self-annotation. Override either field before running if this is wrong."*

**Mismatch handling.** If the target is detected as one of the four but
the user's `model_species` does NOT contain it (e.g. inspect says
`Arabidopsis_thaliana` but config lists `[Homo_sapiens, Mus_musculus]`),
**warn the user explicitly** with a one-line message:

> Species mismatch: inspect suggests the target is **Arabidopsis_thaliana**
> but `model_species` is `[Homo_sapiens, Mus_musculus]`. Recommended: either
> add `Arabidopsis_thaliana` (and consider `skip_blast: true` if it should be
> the only entry) or confirm with the user that cross-species annotation is
> intended.

Do not silently rewrite `model_species` -- that is a biological choice
(`mandatory-rules.md` Sec. 3). The agent may still proceed if the user
confirms; otherwise wait for confirmation.

**ID-namespace preflight (mandatory before `skip_blast: true`).**
Setting `skip_blast: true` means the marker gene IDs go **directly to
the KG** (no BLAST in between), so `adata.raw.var_names` must equal
`KG Gene.Name` with zero tolerance. Verify:

1. `var_names_sample[:5]` from `inspect_h5ad.py` matches the
   per-species format in
   [`data-id-namespace.md`](../data-id-namespace.md) (TAIR locus for
   Arabidopsis, MSU `LOC_Os...` for Oryza, HGNC symbol for human, MGI
   symbol for mouse).
2. For human/mouse: the data uses **gene symbols**, NOT Ensembl IDs.
   Ensembl `var_names` (`ENSG...`, `ENSMUSG...`) with `skip_blast:
   true` will produce ~0% KG coverage -- empirically verified.
3. For `Zea_mays` or `Glycine_max`: **do NOT enable
   `skip_blast: true`** -- KG coverage is too sparse for their
   canonical BLAST-db IDs (see
   [`data-id-namespace.md`](../data-id-namespace.md) ->
   "BLAST-id-only species"). Either keep BLAST on and add a
   KG-richer `model_species` (`Oryza_sativa` / `Triticum_aestivum` for
   maize; `Medicago_truncatula` for soybean), or set
   `skip_blast: true` only when the user accepts the expected
   near-zero annotation as a known limitation.

If any of the three checks fails, **stop and warn the user** --
`skip_blast: true` on mismatched IDs is the most common cause of
"pipeline ran successfully but every cluster is unannotated".

#### Worked example: target IS a model species (with `skip_blast: true`)

For an Arabidopsis root dataset where the user (or the agent) chooses pure
self-annotation:

```yaml
cluster_key: leiden
model_species:
  - Arabidopsis_thaliana   # target species itself -- highest KG coverage
# non_model_fasta omitted -- skip_blast: true makes it optional
non_model_h5ad: edf.h5ad
organ: Root
outdir: output/edf
skip_blast: true           # skip BLASTP, use gene IDs as KG keys directly
```

#### When NOT to use this shortcut

- **You are keeping a close relative alongside** (e.g. `Brassica_rapa` with
  `Arabidopsis_thaliana`). BLASTP is still needed to map the Arabidopsis
  marker gene IDs onto the Brassica KG keys (different gene-ID namespace);
  do **not** set `skip_blast: true` in this hybrid case. Use the
  [previous section](#worked-example-target-is-a-model-species) config.
- **The detected species is NOT one of the four in the table above.**
  Self-mapping against a non-KG-native reference will silently collapse
  the marker gene IDs to whatever you feed in, with poor KG coverage.
  In that case pick a phylogenetic relative from the
  [Phylogenetic distance tables](#phylogenetic-distance-table-plants) and
  let BLASTP run normally.
- **You are unsure.** Single weak signal (e.g. only the file path) -- ask
  the user to confirm the target species before deciding.

#### Verifying the candidate

Before applying the shortcut, the agent should always:

1. Run `python scripts/list_species.py` and confirm the candidate appears
   in the output (canonical name match).
2. Cross-reference the candidate against the four-species table above.
3. Spot-check a few marker gene IDs (from `marker_gene.csv` or the
   inspect output) against the candidate's gene-ID format.

