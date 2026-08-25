#!/usr/bin/env python3
"""Step 1: Extract marker genes from clustered single-cell data.

CLI wrapper used by the Xener agent skill. Reads an .h5ad file with cluster
labels in adata.obs, runs Xener's marker gene identification, and writes a
marker_gene.csv checkpoint to --outdir.

Skill context: this is the first of five steps in the Xener pipeline. It is
invoked by `scripts/run_pipeline.py` (the full pipeline) or called directly
when iterating on parameters. See skill/xener/references/workflows/step-by-step.md
for the full workflow and references/parameters.md for CLI flag details.
"""

import argparse
import os
import sys
import pandas as pd
import scanpy as sc

from _xener_init import build_xener, add_init_config_arg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to .h5ad file")
    parser.add_argument(
        "--cluster-key", default="leiden",
        help="Column in adata.obs storing cluster labels. Defaults to 'leiden'. "
             "If 'leiden' is not in adata.obs, xener's internal process() will "
             "auto-run PCA -> neighbors -> leiden -> UMAP on the .X layer and "
             "write the resulting labels back into adata.obs['leiden'] before "
             "rank_genes_groups. So passing --cluster-key leiden is the correct "
             "way to annotate an h5ad with no precomputed clustering (see "
             "references/workflows/inspection.md). Other values must already "
             "exist as a column in adata.obs."
    )
    parser.add_argument("--outdir", required=True, help="Output directory")
    add_init_config_arg(parser)
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    adata = sc.read(args.input)
    if args.cluster_key not in adata.obs.columns:
        # The xener library supports cluster_key='leiden' even when obs has
        # no such column: its internal process() runs PCA + neighbors +
        # leiden + UMAP on demand. Tell the user we're about to do that, so
        # the I/O + leiden cost isn't a surprise on a multi-GB h5ad.
        if args.cluster_key == "leiden":
            print(f"[INFO] '{args.cluster_key}' not in adata.obs; xener will "
                  f"auto-run PCA -> neighbors -> leiden -> UMAP on the .X "
                  f"layer before marker detection. This may take a few "
                  f"minutes on a multi-GB h5ad.", flush=True)
        else:
            print(f"[ERROR] cluster_key '{args.cluster_key}' not in adata.obs "
                  f"and is not 'leiden' (only 'leiden' triggers xener's "
                  f"auto-clustering path). Available obs columns: "
                  f"{list(adata.obs.columns)}", flush=True)
            sys.exit(2)
    annor, _src = build_xener(init_config=args.init_config)

    markers, debug_markers = annor.get_markers(
        adata=adata,
        cluster_key=args.cluster_key,
    )

    output_path = os.path.join(args.outdir, "marker_gene.csv")
    markers.to_csv(output_path, index=False)
    print(f"Marker genes saved to {output_path}")
    print(f"Shape: {markers.shape}")


if __name__ == "__main__":
    main()