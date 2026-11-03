"""Save coordinate-median fusion of five blind fits, without reference GPS."""

import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, OUTPUT


def run():
    paths = [OUTPUT / f"DSX01-S{i:02d}/refined_endpoints.json" for i in range(1, 6)]
    if not all(p.exists() for p in paths):
        raise RuntimeError("all five fitted endpoints required")
    fits = [json.loads(p.read_text()) for p in paths]
    result = {}
    for arm in ["c0", "fitted_c"]:
        for method in METHODS:
            coordinates = np.array(
                [
                    [f[f"{arm}/{method}"]["latitude_deg"], f[f"{arm}/{method}"]["longitude_deg"]]
                    for f in fits
                ]
            )
            center = np.median(coordinates, axis=0)
            result[f"{arm}/{method}"] = dict(
                latitude_deg=float(center[0]),
                longitude_deg=float(center[1]),
                estimator="coordinate-wise median of five independently fitted scan positions",
                joint_likelihood_refit=False,
                reference_coordinate_used=False,
            )
    write(
        OUTPUT / "blind_position_consensus.json",
        dict(
            estimates=result,
            source_sha256={
                str(p.relative_to(OUTPUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in paths
            },
            stationary_site_assumption=True,
            no_ground_truth_coordinate_in_fusion=True,
        ),
    )


if __name__ == "__main__":
    run()
