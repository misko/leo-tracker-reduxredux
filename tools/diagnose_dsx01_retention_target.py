"""Known-site retention capability only; never a localization search input."""

import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import OUTPUT, ROOT, Scan


def run():
    source = (
        ROOT
        / "reports/2026_10_17_s01_shared_satellite_prototypes"
        / "prior_orbit_em/fitted_c/association.json"
    )
    original = next(
        r for r in json.loads(source.read_text())["rows"] if r["component"] == "S01-RX1-CH2-T000"
    )
    scan = Scan("DSX01-S01")
    i = next(k for k, t in enumerate(scan.tracks) if t["key"] == original["component"])
    # Reconstruct the model-subtracted, alias-lifted CFO from its saved residual
    # and profiled Gaussian constant. No geographic or identity search occurs.
    observed = np.array(original["residual_hz"]) + original["bias_hz"]
    models = {}
    for method in ("shared_phase", "penalized_split", "correlated_noise"):
        terms = scan.curve(i, observed, np.zeros((1, len(observed))), method)
        models[method] = {
            key: terms[field][0]
            for key, field in (
                ("bias", "bias"),
                ("rms", "rms"),
                ("cost", "cost"),
                ("passing", "passing"),
                ("parts", "parts"),
                ("split_at", "split_at"),
                ("residual_hz", "residual"),
                ("innovations_hz", "innovations"),
            )
        }
    write(
        OUTPUT / "target_frozen_state_prototypes.json",
        dict(
            use="known-site frozen-state diagnostic; never supplied to localization search",
            source=str(source.relative_to(ROOT)),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            component=original["component"],
            candidate_norad=original["candidate_norad"],
            models=models,
        ),
    )


if __name__ == "__main__":
    run()
