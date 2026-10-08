"""Independent exact-coincidence clock audit; no satellite-identity pair selection."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import Hard60Objective, HARD60_SCORE  # noqa: E402
from pipeline import InitialClockObjective  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import load_member  # noqa: E402
from leo.analysis.regional_position_score import circular  # noqa: E402
# isort: on


def describe(values):
    values = np.asarray(values)
    if not len(values):
        return dict(count=0)
    return dict(
        count=len(values),
        median_signed_hz=float(np.median(values)),
        median_absolute_hz=float(np.median(abs(values))),
        p90_absolute_hz=float(np.percentile(abs(values), 90)),
        fraction_within_hz={str(h): float(np.mean(abs(values) <= h)) for h in (125, 250, 500)},
    )


def main(label):
    plan = json.loads((HERE / "protocol.json").read_text())
    for f, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError("Preserve first independent clock audit")
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == label))
    prior = json.loads((REPORTS / "2026_10_08_position_error_iter32/protocol.json").read_text())
    binding = prior["cases"][label]
    source = json.loads((REPORTS / binding["document"]).read_text())
    document = source["document"] if binding["nested_document"] else source
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    cal = document["diagnostics"]["calibrations"][binding["basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in selected["satellites"]])
    obs = case.prepared.observations
    groups = {}
    for i in range(len(obs.times_s)):
        key = (int(round(float(obs.times_s[i]) * 1000)), float(obs.rf_hz[i]))
        groups.setdefault(key, {}).setdefault(int(obs.receiver[i]), []).append(i)
    singleton = [
        dict(key=key, i0=rx[0][0], i1=rx[1][0])
        for key, rx in sorted(groups.items())
        if len(rx.get(0, [])) == len(rx.get(1, [])) == 1
    ]
    rng = np.random.Generator(np.random.PCG64(plan["seed"]))
    for row in singleton:
        eligible = [
            r
            for r in singleton
            if r["key"][1] == row["key"][1]
            and abs(obs.times_s[r["i1"]] - obs.times_s[row["i0"]]) >= 30
        ]
        row["null_i1"] = None if not eligible else eligible[int(rng.integers(len(eligible)))]["i1"]
    i0 = np.array([r["i0"] for r in singleton], dtype=int)
    i1 = np.array([r["i1"] for r in singleton], dtype=int)
    mask = np.array([r["null_i1"] is not None for r in singleton], dtype=bool)
    j1 = np.array([r["null_i1"] for r in singleton if r["null_i1"] is not None], dtype=int)
    rows = json.loads(
        (REPORTS / "2026_10_08_position_error_iter33/results" / f"{label}.json").read_text()
    )["candidates"]
    results = []
    for row in rows:
        if row["relative_sigma_s"] not in plan["sigmas_s"]:
            continue
        base = Hard60Objective(
            obs,
            bank,
            case.prior,
            replace(HARD60_SCORE, relative_sigma_s=row["relative_sigma_s"]),
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        model = InitialClockObjective(
            base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
        )
        vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
        value = model.evaluate_joint(vector, clock)[0]
        np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
        nuisance = model.baseline + model.design @ vector[2:7] + model.clock_design @ clock
        corrected = obs.measured_hz - nuisance
        differences = circular(corrected[i1] - corrected[i0])
        control = circular(corrected[j1] - corrected[i0[mask]])
        result = dict(
            arm=row["arm"],
            initialization=row["initialization"],
            relative_sigma_s=row["relative_sigma_s"],
            error_km=row["error_km"],
            all_coincident=describe(differences),
            matched_coincident=describe(differences[mask]),
            mismatched_time=describe(control),
            residual_hz=differences.tolist(),
            null_residual_hz=control.tolist(),
            predicted_receiver_difference_hz=(nuisance[i1] - nuisance[i0]).tolist(),
        )
        results.append(result)
        print(
            label,
            row["relative_sigma_s"],
            row["initialization"],
            row["arm"],
            result["matched_coincident"],
            "null",
            result["mismatched_time"],
            flush=True,
        )
    coverage = dict(
        observation_count=len(obs.times_s),
        group_count=len(groups),
        unmatched_groups=sum(0 not in rx or 1 not in rx for rx in groups.values()),
        multiple_row_groups=sum(
            0 in rx and 1 in rx and (len(rx[0]) != 1 or len(rx[1]) != 1) for rx in groups.values()
        ),
        singleton_pairs=len(singleton),
        null_eligible_pairs=int(mask.sum()),
    )
    write_json(
        output,
        dict(
            label=label,
            scope=plan["scope"],
            coverage=coverage,
            candidates=results,
            pairs=[
                dict(
                    time_s=float(obs.times_s[r["i0"]]),
                    rf_hz=r["key"][1],
                    i0=r["i0"],
                    i1=r["i1"],
                    null_i1=r["null_i1"],
                    time_separation_s=float(obs.times_s[r["i1"]] - obs.times_s[r["i0"]]),
                    null_separation_s=None
                    if r["null_i1"] is None
                    else float(obs.times_s[r["null_i1"]] - obs.times_s[r["i0"]]),
                    measured_difference_hz=float(
                        circular(obs.measured_hz[r["i1"]] - obs.measured_hz[r["i0"]])
                    ),
                )
                for r in singleton
            ],
        ),
    )


if __name__ == "__main__":
    main(sys.argv[1])
