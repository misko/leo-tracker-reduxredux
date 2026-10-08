"""Post-hoc saved-fit decomposition; no optimization or reference-position inputs."""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "2026_10_08_position_error_iter25"
sys.path.insert(0, str(PARENT))
# isort: off
from inputs25 import load  # noqa: E402
from dynamic_rf import DynamicRFObjective  # noqa: E402
from inputs import write_json  # noqa: E402
from slope_prior import SlopePrior  # noqa: E402
# isort: on


def decompose(model, row):
    clock = np.asarray(row["clock_coefficients"])
    value, _, _, terms = model.evaluate_joint(np.asarray(row["vector"]), clock)
    np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
    assigned = model.bank.numbers[terms.responsibilities.argmax(axis=1)].copy()
    assigned[terms.responsibilities.max(axis=1) < 0.5] = 0
    mass = terms.responsibilities.sum(axis=0)
    record = dict(
        objective=float(value),
        data_nll=float(terms.nll),
        signal_mass=float(mass.sum()),
        unassigned=int((assigned == 0).sum()),
        raw_converged=row["converged"],
        satellites={
            str(int(n)): dict(mass=float(mass[i]), assigned_windows=int((assigned == n).sum()))
            for i, n in enumerate(model.bank.numbers)
        },
    )
    if isinstance(model, SlopePrior):
        coefficients = clock[model.slope_slice]
        physical = model.physical_corrections(clock)[1]
        record.update(
            slope_penalty=float(
                0.5
                * coefficients
                @ model.precision[model.slope_slice, model.slope_slice]
                @ coefficients
            ),
            bound_coordinates=int((abs(coefficients) >= 2000 - 1e-5).sum()),
            slopes_hz_s={str(int(n)): float(physical[i]) for i, n in enumerate(model.bank.numbers)},
        )
    return record


def main():
    summary = json.loads((HERE / "summary.json").read_text())
    protocol = json.loads((HERE / "protocol.json").read_text())
    parent = json.loads((PARENT / "protocol.json").read_text())
    selected = {"DS17-008", "LATER-005"}
    reasons = {}
    for variant in protocol["variants"]:
        worst = max(
            summary["cases"],
            key=lambda r: (
                r["arms"]["fitted-c"][variant]["error_km"]
                - r["arms"]["fitted-c"]["control"]["error_km"]
            ),
        )["label"]
        selected.add(worst)
        reasons[variant] = worst
    cases = {}
    for label in sorted(selected):
        old = json.loads((PARENT / "results" / f"{label}.json").read_text())
        new = json.loads((HERE / "results" / f"{label}.json").read_text())
        _, _, base, correction, _, _, _ = load(label, parent)
        models = dict(
            control=DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
        )
        models.update(
            {
                v: SlopePrior(
                    base, correction["nodes_s"], correction["knots_hz"], new["centers_s"], sigma
                )
                for v, sigma in protocol["variants"].items()
            }
        )
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            rows = {}
            for variant, model in models.items():
                source = old if variant == "control" else new
                row = next(
                    r for r in source["candidates"] if r["variant"] == variant and r["arm"] == arm
                )
                rows[variant] = decompose(model, row)
            for variant in protocol["variants"]:
                rows[variant]["mass_changes"] = sorted(
                    [
                        dict(
                            satellite=int(n),
                            mass_delta=rows[variant]["satellites"][n]["mass"] - old_sat["mass"],
                        )
                        for n, old_sat in rows["control"]["satellites"].items()
                    ],
                    key=lambda r: -r["mass_delta"],
                )
            arms[arm] = rows
        cases[label] = arms
        print(label, "saved objectives reconstructed", flush=True)
    write_json(
        HERE / "diagnostics.json",
        dict(
            scope=(
                "Post-hoc raw saved-fit decomposition; no refitting; "
                "cases selected using reported errors"
            ),
            largest_regression_by_variant=reasons,
            cases=cases,
        ),
    )


if __name__ == "__main__":
    main()
