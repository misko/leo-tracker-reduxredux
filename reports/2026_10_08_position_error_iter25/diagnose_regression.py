"""Post-hoc decomposition of the largest regression; no new fitting or oracle seed."""

import json
from pathlib import Path

import numpy as np
from inputs25 import load

# isort: off
from dynamic_rf import DynamicRFObjective
from satellite_correction import SatelliteCorrection
from inputs import write_json
# isort: on

HERE = Path(__file__).resolve().parent


def main():
    label = "LATER-005"
    protocol = json.loads((HERE / "protocol.json").read_text())
    saved = json.loads((HERE / "results" / f"{label}.json").read_text())
    _, _, base, correction, _, _, _ = load(label, protocol)
    models = dict(
        control=DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50),
        slope=SatelliteCorrection(
            base, correction["nodes_s"], correction["knots_hz"], saved["centers_s"], "slope"
        ),
    )
    output = {}
    for arm in ("fitted-c", "zero-c"):
        rows = {}
        for variant, model in models.items():
            row = next(
                r for r in saved["candidates"] if r["variant"] == variant and r["arm"] == arm
            )
            vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
            value, _, _, terms = model.evaluate_joint(vector, clock)
            np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
            maximum = terms.responsibilities.argmax(axis=1)
            assigned = model.bank.numbers[maximum].copy()
            assigned[terms.responsibilities.max(axis=1) < 0.5] = 0
            mass = terms.responsibilities.sum(axis=0)
            record = dict(
                data_nll=float(terms.nll),
                objective=float(value),
                all_nuisance_penalty=row["calibration_penalty"],
                signal_mass=float(mass.sum()),
                unassigned=int((assigned == 0).sum()),
                satellites={
                    str(int(n)): dict(
                        mass=float(mass[i]), assigned_windows=int((assigned == n).sum())
                    )
                    for i, n in enumerate(model.bank.numbers)
                },
            )
            if variant == "slope":
                coefficients = clock[model.slope_slice]
                physical = model.physical_corrections(clock)[1]
                record.update(
                    satellite_slope_penalty=float(
                        0.5
                        * coefficients
                        @ model.precision[model.slope_slice, model.slope_slice]
                        @ coefficients
                    ),
                    largest_coordinate_hz_per_100s=float(max(abs(coefficients))),
                    bound_coordinates=int((abs(coefficients) >= 2000 - 1e-5).sum()),
                    slopes_hz_s={
                        str(int(n)): float(physical[i]) for i, n in enumerate(model.bank.numbers)
                    },
                )
            rows[variant] = record
        rows["mass_changes"] = sorted(
            [
                dict(
                    satellite=int(n),
                    mass_delta=rows["slope"]["satellites"][n]["mass"] - old["mass"],
                    control_assigned=old["assigned_windows"],
                    slope_assigned=rows["slope"]["satellites"][n]["assigned_windows"],
                )
                for n, old in rows["control"]["satellites"].items()
            ],
            key=lambda row: -row["mass_delta"],
        )
        output[arm] = rows
    write_json(
        HERE / "largest-regression.json",
        dict(
            label=label,
            arms=output,
            scope="Post-hoc association decomposition; no refitting or reference-position inputs",
        ),
    )
    for arm, rows in output.items():
        print(
            arm,
            "mass gains",
            rows["mass_changes"][:4],
            "slope penalty",
            rows["slope"]["satellite_slope_penalty"],
            "bounds",
            rows["slope"]["bound_coordinates"],
        )


if __name__ == "__main__":
    main()
