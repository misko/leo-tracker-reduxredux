"""Frozen 119-member control versus satellite slope experiment, with strict c ablation."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

# Import input bootstrap before the frozen report modules it exposes.
# isort: off
from inputs25 import REPORTS, load

from dynamic_rf import DynamicRFObjective, fit
from inputs import json_value, write_json
from probe import error_km
from satellite_correction import SatelliteCorrection
# isort: on

HERE = Path(__file__).resolve().parent


def run(label, protocol):
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        print(label, "already complete", flush=True)
        return
    binding = protocol["members"][label]
    if "reuse" in binding:
        source = REPORTS / binding["reuse"]
        prior = json.loads(source.read_text())
        write_json(
            path,
            dict(
                label=label,
                cohort=binding["cohort"],
                reused_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                centers_s=prior["centers_s"],
                satellites=prior["satellites"],
                previous_operational=prior["previous_operational"],
                candidates=[r for r in prior["candidates"] if r["variant"] in ("control", "slope")],
            ),
        )
        print(label, "sealed pilot reused", flush=True)
        return
    case, document, base, correction, seed, clock, receipt = load(label, protocol)
    control = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    value, _, _, terms = control.evaluate_joint(seed, clock)
    if receipt["source_stage"] != "remove-5":
        np.testing.assert_allclose(value, receipt["source_objective"], atol=1e-6, rtol=0)
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ base.observations.times_s,
        mass,
        out=np.full(len(mass), base.observations.time_center_s),
        where=mass > 1e-12,
    )
    rows = []
    for variant in ("control", "slope"):
        model = (
            control
            if variant == "control"
            else SatelliteCorrection(
                base, correction["nodes_s"], correction["knots_hz"], centers, "slope"
            )
        )
        start_clock = clock if variant == "control" else model.expand_clock(clock)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=start_clock))
            row.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, row["vector"], document)
            )
            if variant == "slope":
                offsets, slopes = model.physical_corrections(np.asarray(row["clock_coefficients"]))
                row.update(
                    satellite_offsets_hz=offsets.tolist(), satellite_slopes_hz_s=slopes.tolist()
                )
            if arm == "zero-c":
                assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
            rows.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 5), flush=True)
    write_json(
        path,
        dict(
            label=label,
            cohort=binding["cohort"],
            candidates=rows,
            centers_s=centers.tolist(),
            satellites=base.bank.numbers.tolist(),
            **receipt,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    shard = int(sys.argv[1])
    assert shard in range(4)
    for label in list(protocol["members"])[shard::4]:
        run(label, protocol)
