"""Bounded C1-Q1/T1AT comparison across all archived basins of one live scan.

Print numerical receipts; external caller chooses a new output file. No live
store writes. Fixed seeds are both archived T1AT fitted-c finals per basin.
"""
# The sibling research helper is loaded after adding its explicit directory.
# ruff: noqa: E402

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "timing"))
from inputs import load
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.application.regional_position_runner import json_value
from leo.contracts.regional_position import POSITION_SCORES
from model import C1Q1Objective


def distance(lat, lon, reference):
    a, b, c, d = map(math.radians, (lat, lon, *reference))
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 12742017.6 * math.asin(math.sqrt(min(1, h)))


def main():
    session = "scan-fw-ffe5accf2d020263"
    data = load(session)
    doc, obs, prior = data["doc"], data["observations"], data["prior"]
    finals = [
        f
        for f in doc["diagnostics"]["final_starts"]
        if f["method"] == "T1AT" and f["arm"] == "fitted-c" and f["fit"]
    ]
    rows, parity = [], []
    begun = time.monotonic()
    for key, basin in sorted(data["basins"].items()):
        seeds = [f for f in finals if f["basin"] == key]
        control = PositionObjective(
            obs,
            basin["bank"],
            prior,
            POSITION_SCORES["T1AT"],
            receiver_baseline_hz=basin["baseline"],
        )
        challenger = C1Q1Objective(
            obs, basin["bank"], prior, receiver_baseline_hz=basin["baseline"]
        )
        for seed in seeds:
            delta = control.evaluate(seed["fit"]["vector"])[0] - seed["fit"]["objective"]
            assert abs(delta) < 1e-6
            parity.append(dict(basin=key, start=seed["start"], delta=delta))
        for name, objective in (("T1AT", control), ("C1-Q1", challenger)):
            for arm in ("zero-c", "fitted-c"):
                for seed in seeds:
                    fit = fit_position(
                        objective,
                        seed["fit"]["vector"],
                        rf_arm=arm,
                        maximum_seconds=5,
                        maximum_iterations=300,
                        local_center=basin["center"],
                        local_radius_km=basin["radius"],
                    )
                    lat, lon = coordinates(prior, fit.vector[:2])
                    penalty = 0.5 * (fit.vector[7] / objective.score.common_sigma_s) ** 2
                    penalty += (
                        0.5 * np.sum(fit.vector[8:] ** 2) / objective.score.relative_sigma_s**2
                    )
                    row = dict(
                        session=session,
                        basin=key,
                        model=name,
                        arm=arm,
                        start=seed["start"],
                        score=fit.objective + basin["calibration_penalty"],
                        data_nll=fit.objective - penalty,
                        timing_penalty=float(penalty),
                        calibration_penalty=basin["calibration_penalty"],
                        error_m=distance(
                            lat,
                            lon,
                            (doc["reference_latitude_deg"], doc["reference_longitude_deg"]),
                        ),
                        fit=json_value(fit),
                        bank=basin["numbers"],
                    )
                    rows.append(row)
                    print(
                        name,
                        arm,
                        key,
                        seed["start"],
                        round(row["error_m"]),
                        fit.stop_reason,
                        file=sys.stderr,
                        flush=True,
                    )
    sources = [Path(__file__), HERE / "model.py", HERE.parent / "timing" / "inputs.py"]
    print(
        json.dumps(
            dict(
                session=session,
                rows=rows,
                parity=parity,
                elapsed_s=time.monotonic() - begun,
                protocol=dict(
                    seeds=(
                        "Both archived T1AT fitted-c final vectors per basin; "
                        "same seeds for all arms"
                    ),
                    basins="All six archived successful final basins; no truth selection",
                    seconds_per_fit=5,
                    iterations_per_fit=300,
                    calibration="Shared original fitted-c baseline and bank within each basin",
                    limitation=(
                        "Single scan, archived full-data warm starts and proposals; "
                        "no independent global search"
                    ),
                ),
                input_manifest_sha256=doc["input_manifest_sha256"],
                configuration_sha256=doc["configuration_sha256"],
                snapshot_sha256=doc["diagnostics"]["snapshot_sha256"],
                source_sha256={
                    str(p): "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
                },
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
