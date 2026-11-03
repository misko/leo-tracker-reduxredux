"""Freeze simple multiscan consensus positions without an evaluation site."""

import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from prototype_dsx01_continuous_position import OUTPUT


def run():
    paths = [OUTPUT / f"DSX01-S0{k}" / "endpoints.json" for k in range(1, 6)]
    fits = [json.loads(p.read_text()) for p in paths]
    keys = set(fits[0]).intersection(*(set(f) for f in fits[1:]))
    results = {}
    for key in sorted(keys):
        positions = np.array([[f[key]["latitude_deg"], f[key]["longitude_deg"]] for f in fits])
        for name, operation in (("mean", np.mean), ("coordinate_median", np.median)):
            point = operation(positions, axis=0)
            results[f"{name}/{key}"] = dict(
                latitude_deg=point[0],
                longitude_deg=point[1],
                stationary_site_assumption=True,
                input_scan_count=5,
                evaluation_position_used=False,
                joint_frequency_refit=False,
            )
    write(OUTPUT / "consensus_endpoints.json", results)
    write(
        OUTPUT / "consensus_protocol.json",
        dict(
            reference_position_not_read=True,
            rules=["arithmetic mean", "coordinate-wise median"],
            model_and_c_arms_all_reported=True,
            no_GPS_selection_of_scan_or_method=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            inputs_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        ),
    )


if __name__ == "__main__":
    run()
