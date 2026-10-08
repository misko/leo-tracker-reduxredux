"""Repeat diagnostic continuation with at most two warm retries per failed step."""

import json
import sys

import numpy as np
from profile import HERE, decompose, error_km, load, write_json
from profile_fit import JointClockObjective, fit


def run(label):
    output = HERE / "retried" / f"{label}.json"
    if output.exists():
        return
    initial = json.loads((HERE / "results" / f"{label}.json").read_text())
    case, document, base, _ = load(label)
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)
    chosen = initial["fitted_selected"]
    terms = model.evaluate_joint(
        np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    )[3]
    groups = model.bank.numbers[terms.responsibilities.argmax(axis=1)].copy()
    groups[terms.responsibilities.max(axis=1) < 0.5] = 0
    truth = np.asarray(initial["reference_point_km"])
    origin = np.asarray(chosen["vector"][:2])
    steps = int(np.ceil(np.linalg.norm(truth - origin) / 0.25))
    assert 1 <= steps <= 40
    arms = []
    for arm in ("fitted-c", "zero-c"):
        previous = next(
            r for r in initial["rows"] if r["arm"] == arm and r["phase"] == "selected-fixed"
        )
        assert previous["converged"]
        rows = []
        for i in range(1, steps + 1):
            vector = np.asarray(previous["vector"]).copy()
            vector[:2] = origin + (truth - origin) * (i / steps)
            row = fit(
                model,
                vector,
                arm=arm,
                fixed_position=True,
                clock_seed=previous["clock_coefficients"],
            )
            attempts = [
                dict(
                    converged=row["converged"],
                    stationarity=row["stationarity"],
                    objective=row["objective"],
                )
            ]
            for retry in range(2):
                if row["converged"]:
                    break
                row = fit(
                    model,
                    row["vector"],
                    arm=arm,
                    fixed_position=True,
                    clock_seed=row["clock_coefficients"],
                )
                attempts.append(
                    dict(
                        converged=row["converged"],
                        stationarity=row["stationarity"],
                        objective=row["objective"],
                    )
                )
            row["attempts"] = attempts
            row.update(
                step=i, fraction=i / steps, error_km=error_km(case.prior, row["vector"], document)
            )
            row["decomposition"] = decompose(model, row, groups)
            rows.append(row)
            if not row["converged"]:
                break
            previous = row
        released = None
        if len(rows) == steps and rows[-1]["converged"]:
            best = min(
                [rows[-1]]
                + [
                    r
                    for r in initial["rows"]
                    if r["arm"] == arm
                    and r["phase"].startswith("reference-")
                    and r["phase"] != "reference-released"
                    and r["converged"]
                ],
                key=lambda r: r["objective"],
            )
            released = fit(model, best["vector"], arm=arm, clock_seed=best["clock_coefficients"])
            released["error_km"] = error_km(case.prior, released["vector"], document)
            released["decomposition"] = decompose(model, released, groups)
        arms.append(dict(arm=arm, steps=rows, released=released))
        print(
            label,
            arm,
            "steps",
            len(rows),
            "of",
            steps,
            "last_score",
            rows[-1]["objective"],
            "released_error",
            released["error_km"] if released else None,
            flush=True,
        )
    write_json(output, dict(label=label, step_count=steps, arms=arms))


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
