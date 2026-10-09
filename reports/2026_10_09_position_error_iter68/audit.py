"""Rebuild historical pairs, then inventory ordinary-seed clock proposals."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter67"))
from clock_starts import clock_starts, pair_residuals  # noqa: E402
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    InitialClockObjective,
    load_member,
    read,
    write_json,
)


def make_model(case, document, sigma, numbers=None):
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    cal = document["diagnostics"]["calibrations"][selected["source_basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in (numbers or selected["satellites"])])
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        replace(HARD60_SCORE, relative_sigma_s=sigma),
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    return InitialClockObjective(
        base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
    )


def residuals(model, seed, clock):
    obs = model.observations
    nuisance = (
        model.baseline
        + model.design @ np.asarray(seed)[2:7]
        + model.clock_design @ np.asarray(clock)
    )
    return pair_residuals(
        obs.times_s, obs.rf_hz, obs.receiver, obs.measured_hz, nuisance, obs.time_center_s
    )


def main():
    protocol = read(HERE / "protocol.json")
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first observation/proposal audit")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    bindings = read(REPORTS / "2026_10_08_position_error_iter32/protocol.json")["cases"]
    qualification, cases = [], {}
    for label in protocol["labels"]:
        case = load_member(next(m for m in members if m["label"] == label))
        cases[label] = case
        binding = bindings[label]
        source = read(REPORTS / binding["document"])
        document = source["document"] if binding["nested_document"] else source
        historical = read(REPORTS / "2026_10_08_position_error_iter34/results" / f"{label}.json")
        previous = read(REPORTS / "2026_10_08_position_error_iter33/results" / f"{label}.json")
        for saved in previous["candidates"]:
            if saved["arm"] != "fitted-c" or saved["relative_sigma_s"] not in (2, 0.75):
                continue
            model = make_model(case, document, saved["relative_sigma_s"])
            pairs, times, values = residuals(model, saved["vector"], saved["clock_coefficients"])
            np.testing.assert_array_equal(pairs, [[p["i0"], p["i1"]] for p in historical["pairs"]])
            expected = next(
                r
                for r in historical["candidates"]
                if r["arm"] == "fitted-c"
                and r["relative_sigma_s"] == saved["relative_sigma_s"]
                and r["initialization"] == saved["initialization"]
            )
            np.testing.assert_allclose(values, expected["residual_hz"], atol=1e-7, rtol=0)
            qualification.append(
                dict(
                    label=label,
                    sigma=saved["relative_sigma_s"],
                    initialization=saved["initialization"],
                    pairs=len(pairs),
                    max_residual_difference_hz=float(
                        np.max(abs(values - np.asarray(expected["residual_hz"])))
                    ),
                )
            )
    assert len(qualification) == 8
    print("Historical raw-observation qualification passed", flush=True)
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    case = cases["RESERVED-001"]
    document = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    model = make_model(case, document, 1, census["candidate_union"])
    rows = []
    for index, source in enumerate(census["rows"]):
        row = dict(
            index=index,
            region=source["region"],
            source_arm=source["source_arm"],
            start=source["start"],
            status=source["status"],
        )
        if source["status"] == "feasible":
            pairs, times, values = residuals(model, source["seed"], source["clock"])
            proposals, starts, rejected = clock_starts(source["seed"], times, values)
            row.update(
                pairs=len(pairs),
                proposals=proposals,
                starts=[dict(name=name, vector=vector.tolist()) for name, vector in starts],
                rejected=rejected,
            )
        rows.append(row)
    write_json(
        HERE / "results.json",
        dict(
            qualification=qualification,
            rows=rows,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        ),
    )
    print(
        "Inventoried",
        len(rows),
        "ordinary endpoints without fitting or position evaluation",
        flush=True,
    )


if __name__ == "__main__":
    main()
