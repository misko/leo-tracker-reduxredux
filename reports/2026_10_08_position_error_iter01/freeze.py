"""Freeze scan-level study membership before reading DS17 position outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/local")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / "protocol.json"
    if output.exists():
        raise FileExistsError("study protocol is immutable")
    seal = json.loads((SOURCE / "seal.json").read_text())
    for name, expected in seal["files"].items():
        assert digest(SOURCE / name) == expected, name
    manifest = json.loads((SOURCE / "manifest.json").read_text())
    assert manifest["dataset_id"] == "DS17" and len(manifest["captures"]) == 51
    rows = manifest["captures"]
    # One outcome was seen in live deployment verification; reserve the second
    # operational canary too, so browser verification cannot contaminate holdout.
    known = {"scan-fw-85e3bfb9e4cfcd46", "scan-fw-da79d96a4515ec30"}
    population = [r["session_id"] for r in rows if r["session_id"] not in known]
    rng = np.random.Generator(np.random.PCG64(2026100802))
    development = known | set(rng.choice(population, size=15, replace=False).tolist())
    protocol = {
        "created_utc": datetime.now(UTC).isoformat(),
        "objective": "Reduce position error toward <1 km mean without reference-guided inference",
        "baseline_runtime": "7d296d36d733a18fbc4ec28c63dc579ef2f7f136",
        "baseline_configuration": (
            "sha256:d1524c45e6e702008221d941240e7a0ac26f13feac87fef73e83f04c9c0a80f6"
        ),
        "ds17_manifest": seal["files"]["manifest.json"],
        "ds17_seal": digest(SOURCE / "seal.json"),
        "random_generator": "numpy.PCG64",
        "seed": 2026100802,
        "group": "whole independent nonoverlapping recording, both receivers together",
        "known_development": sorted(known),
        "known_reason": (
            "live rollout canaries; first outcome seen, second reserved before completion"
        ),
        "ds16_use": (
            "all 48 are previously inspected development/regression data, not unseen validation"
        ),
        "membership": [
            {
                "label": f"DS17-{i:03}",
                "session_id": r["session_id"],
                "capture_start_utc_ns": r["capture_start_utc_ns"],
                "group": "development" if r["session_id"] in development else "validation",
            }
            for i, r in enumerate(rows, 1)
        ],
        "selection": "No admission/exclusion based on localization, fit or analysis readiness",
        "validation_lock": (
            "Do not inspect held-out location errors until candidate policies and tuning are frozen"
        ),
        "ablation": (
            "Each candidate includes matched c=0 versus fitted-c, same observations, "
            "satellites, priors and budget"
        ),
        "metrics": [
            "mean error",
            "median error",
            "p95 error",
            "maximum error",
            "coverage/failures",
            "frequency RMS",
            "score",
            "runtime",
        ],
        "reference_policy": (
            "Reference used for development diagnostics and after inference for evaluation; "
            "never runtime seeds/selection"
        ),
        "initial_hypotheses": [
            "Frozen receiver calibration and association may bias a correct local position fit",
            "Uneven satellite support and correlated measurement errors may over-weight "
            "a few tracks",
            "Likelihood width and outlier handling may favor incorrect associations "
            "despite optimizer convergence",
            "Stationary-receiver multi-scan fusion may reduce random error; must report "
            "separately from single-scan localization",
        ],
        "newer_data": (
            "Record membership before outcome inspection; keep separate operational replication "
            "and do not silently add favorable scans"
        ),
        "rf_collection": "none; saved corpus and existing schedule only",
    }
    output.write_text(json.dumps(protocol, indent=2) + "\n")
    (HERE / "protocol.sha256").write_text(digest(output) + "\n")
    (HERE / "ds17-manifest.json").write_bytes((SOURCE / "manifest.json").read_bytes())
    print(
        json.dumps(
            {
                "development": len(development),
                "validation": 51 - len(development),
                "protocol": digest(output),
            }
        )
    )


if __name__ == "__main__":
    main()
