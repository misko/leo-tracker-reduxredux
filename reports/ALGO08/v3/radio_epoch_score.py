"""Score sealed radio epoch masks, fixed-owner fits and blind joint replays."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import inputs, write
from arc_design_score import outcome, visits
from radio_epoch_trial import CASES, FAMILY_SHA, HERE, project


def source_files(directory):
    names = [f"{case}.json" for case in CASES] + [f"{case}-blind.json" for case in CASES[:2]]
    records = {name: (directory / name).read_bytes() for name in names}
    for case in CASES[:2]:
        path = f"{case}-blind.solver.json"
        if (directory / path).exists():
            records[path] = (directory / path).read_bytes()
    return records


def masked_geometry(native, result):
    probes = native["source"]["probes"]
    plan = result["plan"]
    selection = {key: value for key, value in plan["selection"].items() if key != "trail"}
    if selection["best"] is not None:
        selection["best"] = {key: value for key, value in selection["best"].items() if key != "indices"}
    selection["path_steps"] = len(plan["selection"]["trail"])
    _, published = project(native, plan)
    published["sealed_stereo_windows"] = published.pop("original_visits")
    counts = dict(original=visits(probes, range(len(probes))),
                  **{name: visits(probes, plan[name + "_indices"]) for name in ("core", "paid")})
    audit = dict(result["feasibility"])
    affected = Counter()
    for row in audit["rejected"]:
        for issue in row["issues"]:
            affected[issue] += row["points"]
    audit["unqualified_rows_by_issue"] = dict(affected)
    return dict(selection=selection, feasibility=audit, block_keys=plan["block_keys"], acquisition=counts,
                masked_packet=published)


def score(directory, output):
    from leo.contracts.digests import canonical_digest

    raw = source_files(directory)
    rows = {key: json.loads(blob) for key, blob in raw.items()}
    expected_driver = sha256((HERE / "radio_epoch_trial.py").read_bytes()).hexdigest()
    expected_selection = sha256((HERE / "radio_epoch.py").read_bytes()).hexdigest()
    if any(rows[f"{case}.json"]["driver_sha256"] != expected_driver
           or rows[f"{case}.json"]["selection_sha256"] != expected_selection for case in CASES):
        raise ValueError("Input receipts come from a different frozen study")
    inside, outside = (rows[f"{case}.json"] for case in CASES[:2])
    if (inside["identity"] != outside["authority"] or inside["core_sha256"] != outside["core_sha256"]
            or inside["paid_sha256"] != outside["paid_sha256"]):
        raise ValueError("The omitted offer used a different paid waveform")
    truth = references()
    results = {}
    for case in CASES:
        native, _, _, stock, identity = inputs(case)
        row = rows[f"{case}.json"]
        if row["identity"] != identity:
            raise ValueError("The frozen waveform or offer changed")
        fixed = outcome(row, stock, truth[case])
        fixed["time"] = {key: value for key, value in row.items() if key.endswith("_clocks")}
        if "ordinary" in row:
            fixed["ordinary"] = {arm: {key: value[key] for key in ("east_north_km", "rf_rms_hz", "failed_curved", "failed_linear")}
                                 for arm, value in row["ordinary"].items()}
        if "signed" in row:
            fixed["signed_status"] = row["signed"]["status"]
        results[case] = dict(identity=identity, truth_clearance_km=face_clearance_km(identity["offer"], truth[case]),
                             fixed=fixed, core_sha256=row["core_sha256"], paid_sha256=row["paid_sha256"])
        if case != "south-far":
            results[case]["geometry"] = masked_geometry(native, row)
        if case == "DS30-0008":
            continue
        blind = rows[f"{case}-blind.json"]
        _, plan_stats = project(native, row["plan"])
        decision = blind["decision"]
        if blind["input"] != identity or blind["mask"] != plan_stats or blind["sealed_outcome"] != canonical_digest(decision):
            raise ValueError("Blind fit had a different offer or waveform from its fixed-owner fit")
        inferred = outcome(decision, stock, truth[case])
        path = f"{case}-blind.solver.json"
        inferred["result"] = decision
        if path in rows:
            if decision["full_solver_receipt_sha256"] != sha256(raw[path]).hexdigest():
                raise ValueError("Blind solver receipt bytes do not match the authorized outcome")
            inferred["fallback_cpu_s"] = sum(attempt.get("fallback_clocks", {}).get("cpu_s", 0.)
                                             for attempt in rows[path]["attempts"])
            inferred["routes"] = [dict(decision=attempt["decision"], reason=attempt.get("reason"))
                                   for attempt in rows[path]["attempts"]]
        results[case]["blind"] = inferred
    pins = {str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
            for path in (PHYSICAL, SIMULATED)}
    write(output, dict(cases=results, pins=pins, candidate_receipts={key: sha256(blob).hexdigest()
                                                                  for key, blob in raw.items()},
                       worker=inside["host"], whole_families_sha256=FAMILY_SHA,
                       trial_sha256=expected_driver, selector_sha256=expected_selection))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    score(**vars(parser.parse_args()))
