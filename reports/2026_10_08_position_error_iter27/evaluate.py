"""Matched tighter-slope-prior experiment on all119 consumed scans."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter25"))
# isort: off
from inputs25 import load  # noqa: E402
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
from slope_prior import SlopePrior  # noqa: E402
# isort: on


def run(label, protocol, parent):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        print(label, "already complete", flush=True)
        return
    previous = json.loads(
        (REPORTS / "2026_10_08_position_error_iter25/results" / f"{label}.json").read_text()
    )
    case, document, base, correction, seed, clock, receipt = load(label, parent)
    control = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    _, _, _, terms = control.evaluate_joint(seed, clock)
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ base.observations.times_s,
        mass,
        out=np.full(len(mass), base.observations.time_center_s),
        where=mass > 1e-12,
    )
    np.testing.assert_allclose(centers, previous["centers_s"], atol=1e-9, rtol=0)
    assert base.bank.numbers.tolist() == previous["satellites"]
    candidates = []
    for variant, sigma in protocol["variants"].items():
        model = SlopePrior(base, correction["nodes_s"], correction["knots_hz"], centers, sigma)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=model.expand_clock(clock)))
            row.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, row["vector"], document)
            )
            row["satellite_slopes_hz_s"] = model.physical_corrections(
                np.asarray(row["clock_coefficients"])
            )[1].tolist()
            if arm == "zero-c":
                assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
            candidates.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 5), flush=True)
    write_json(
        output,
        dict(
            label=label,
            cohort=parent["members"][label]["cohort"],
            candidates=candidates,
            satellites=base.bank.numbers.tolist(),
            centers_s=centers.tolist(),
            **receipt,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    parent = json.loads((REPORTS / "2026_10_08_position_error_iter25/protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    shard = int(sys.argv[1])
    assert shard in range(4)
    for label in protocol["labels"][shard::4]:
        run(label, protocol, parent)
