"""Copy compact, immutable experiment evidence; never copy raw IQ or stage caches.

Usage: python collect_evidence.py /path/to/original/reports
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = (
    "recent_filter_review",
    "fit_root_cause",
    "debug_timing_prior",
    "debug_search_boundary",
    "debug_search_gap",
    "debug_shared_bias",
    "bad_sample_options",
    "sigma1_root_cause",
    "sigma1_cones",
    "cone_failure_debug",
    "adaptive_drift_8h",
    "slope_priors",
    "2139_slope_cutoffs",
    "systematic_starts",
    "single_method_grid",
    "n64_before_after",
    "n64_sigma_slope_variants",
    "n64_soft_slope_priors",
    "hard60_root_cause",
    "hard60_variants",
)
FIGURES = {
    "recent_filter_review": ["review.png"],
    "fit_root_cause": ["diagnosis.png"],
    "bad_sample_options": ["comparison.png"],
    "sigma1_root_cause": ["boundary_geometry.png", "likelihood_diagnosis.png"],
    "cone_failure_debug": ["clock_repair.png"],
    "adaptive_drift_8h": ["drift_distribution.png", "drift_timeline.png"],
    "single_method_grid": ["edge_priority/edge_priority_comparison.png"],
    "n64_before_after": ["position_comparison.png"],
    "n64_sigma_slope_variants": ["position_comparison.png", "per_scan_errors.png"],
    "n64_soft_slope_priors": [
        "accuracy_summary.png",
        "prior_shapes.png",
        "frequency_vs_position.png",
    ],
    "hard60_root_cause": ["n29_likelihood_profile.png", "coarse_local_minima.png"],
    "hard60_variants": ["position_error_cdf.png", "paired_position_errors.png"],
}


def main(root):
    root = Path(root)
    inventory = []
    for study in STUDIES:
        source = root / ("2026_10_07_" + study)
        selected = [
            p
            for p in source.iterdir()
            if p.is_file()
            and (
                p.suffix in (".txt", ".csv")
                or p.name
                in (
                    "summary.json",
                    "validation.json",
                    "validation_full.json",
                    "protocol.json",
                    "protocol_full.json",
                    "protocol_holdout.json",
                    "holdout_summary.json",
                    "cohort.json",
                    "recipe.json",
                )
            )
        ]
        selected += [source / name for name in FIGURES.get(study, ())]
        for path in sorted(selected):
            if path.stat().st_size > 3_000_000:
                raise ValueError(f"unexpectedly large compact artifact: {path}")
            relative = Path("evidence") / study / path.relative_to(source)
            destination = HERE / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            inventory.append(
                {
                    "path": str(relative),
                    "source": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    (HERE / "evidence_manifest.json").write_text(
        json.dumps({"artifacts": inventory}, indent=2) + "\n"
    )
    print(
        f"Copied {len(inventory)} compact artifacts; "
        f"{sum(row['bytes'] for row in inventory):,} bytes"
    )


if __name__ == "__main__":
    main(sys.argv[1])
