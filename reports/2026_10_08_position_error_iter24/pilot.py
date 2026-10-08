"""Matched non-oracle fits of three satellite correction hypotheses."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter20"))
# isort: off
from newer import load_member  # noqa: E402
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from satellite_correction import SatelliteCorrection  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
# isort: on

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402


def run(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    binding = protocol["cases"][label]
    previous = json.loads((REPORTS / binding["result"]).read_text())["result"]
    document = json.loads((REPORTS / binding["baseline"]).read_text())
    members = json.loads(
        (REPORTS / "2026_10_08_position_error_iter20/validation-protocol.json").read_text()
    )["members"]
    case = load_member(next(row for row in members if row["label"] == label))
    assert canonical_digest(case.document) == canonical_digest(document)
    assert previous["regional_sources"]["fitted-c"] == "baseline"
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in previous["satellites"]])
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    correction = calibration["correction"]
    control = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    chosen = previous["stages"]["drift-50"]["fitted-c"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    value, _, _, terms = control.evaluate_joint(seed, clock)
    np.testing.assert_allclose(value, chosen["objective"], atol=1e-6, rtol=0)
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ base.observations.times_s,
        mass,
        out=np.full(len(mass), base.observations.time_center_s),
        where=mass > 1e-12,
    )
    rows = []
    for variant in protocol["variants"]:
        model = (
            control
            if variant == "control"
            else SatelliteCorrection(
                base, correction["nodes_s"], correction["knots_hz"], centers, variant
            )
        )
        start_clock = clock if variant == "control" else model.expand_clock(clock)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=start_clock))
            row.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, row["vector"], document)
            )
            if variant != "control":
                offsets, slopes = model.physical_corrections(np.asarray(row["clock_coefficients"]))
                row.update(
                    satellite_offsets_hz=offsets.tolist(), satellite_slopes_hz_s=slopes.tolist()
                )
            if arm == "zero-c":
                assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
            rows.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 6), flush=True)
    write_json(
        HERE / "results" / f"{label}.json",
        dict(
            label=label,
            centers_s=centers.tolist(),
            satellites=bank.numbers.tolist(),
            previous_operational=previous["operational"],
            candidates=rows,
            reference_use="Post-fit error reporting only; never initializer or selection input",
        ),
    )


if __name__ == "__main__":
    run(sys.argv[1])
