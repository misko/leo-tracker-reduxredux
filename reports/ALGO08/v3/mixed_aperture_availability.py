"""Gate a mixed-duration receiver with the actually available full-aperture primary factors."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from aperture_trial import ARMS, read, write
from full_family_amortized_trial import run as fit
from mixed_stereo_paid import checked_exterior
from paid_certified_trial import GRAPH, PAIRED_FIELDS, check_binding, sealed
from paid_graph_trial import prepare_paid
from sparse_consensus_trial import CASES, bound_inputs


HERE = Path(__file__).resolve().parent
CONTROL_SHA = "1bdaf3976abeb36bf919652e495b4d63f0739a9cd6edd12695dea1356ffb9d37"
MODE = "full_primary_availability"


def select(rows, clocks, *, all_times=False, all_ranks=False):
    from leo.contracts.digests import canonical_digest

    if len(rows) != len(clocks):
        raise ValueError("Missing measured lane clocks")
    visits, last, lane_counts, native_ns = Counter(), {}, Counter(), Counter()
    ranks, eligible_counts = Counter(), Counter()
    mask, picks = [], []
    common = ("channel", "actual_rf_hz", "edge", "visit_index", "valid_start_counter")
    seen = set()
    for i, (left, right) in enumerate(zip(rows[::2], rows[1::2], strict=True)):
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1) or any(left[k] != right[k] for k in common)
                or left["visit_index"] in seen):
            raise ValueError("Expected unique chronological stereo visits")
        seen.add(left["visit_index"])
        key = tuple(left[k] for k in common[:3])
        counter = left["valid_start_counter"]
        if key in last and counter <= last[key]:
            raise ValueError("RF stream counters must increase")
        last[key] = counter
        index = visits[key] % 8
        visits[key] += 1
        retained = all_times or index == 0 or index % 2
        mode = ("skip" if not retained else "full" if index == 0 or all_ranks else "primary")
        mask.append((left["visit_index"], mode))
        for j, row in enumerate((left, right)):
            lane_counts[mode] += 1
            native_ns[mode] += clocks[2 * i + j]
            eligible = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True
                        and (mode == "full" or mode == "primary" and c["candidate_rank"] == 0)]
            eligible_counts[mode] += len(eligible)
            if eligible:
                strongest = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
                ranks[str(strongest["candidate_rank"])] += 1
                picks.append([strongest])
            else:
                picks.append([])
    return picks, dict(counts=lane_counts, full_call_cpu_s_by_slot={k: n / 1e9 for k, n in native_ns.items()},
                       mask_sha256=canonical_digest(mask), ranks=ranks, eligible_factors=eligible_counts)


def prepare(case):
    from leo.contracts.digests import canonical_digest

    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    identity.update(native_sha256=canonical_digest(native))
    check_binding(identity, sealed("complete")[case]["complete"]["identity"], "complete")
    complete = identity["native_sha256"]
    cpu = process_time()
    native, _, selection = prepare_paid(native, rows, clocks, identity, MODE, select_paid=select)
    selection["charged_selection_cpu_s"] = process_time() - cpu
    identity.update(mode=MODE, graph_parameters=GRAPH, selection=selection, complete_native_sha256=complete,
                    native_sha256=canonical_digest(native), all_native_cpu_s=sum(clocks) / 1e9)
    return native, archive, offer, identity, True


def score(directory, summary, archive):
    from aperture_score import PHYSICAL, references
    from mixture_score import section
    from signed_0374_transfer import owner_changes

    blob = (HERE / "measurements/mixed-stereo-paid.json.gz").read_bytes()
    if sha256(blob).hexdigest() != CONTROL_SHA:
        raise ValueError("Complete saved controls changed")
    controls = json.loads(gzip.decompress(blob))["runs"]
    paths = {case: directory / f"{case}.json" for case in CASES}
    rows = {case: read(path) for case, path in paths.items()}
    for case, row in rows.items():
        base = controls[case]["complete"]["identity"]
        if (any(row["identity"][k] != base[k] for k in PAIRED_FIELDS)
                or row["identity"]["complete_native_sha256"] != base["native_sha256"]):
            raise ValueError("Original measurement, offer or causal archive differs")
    if rows["south-far"]["identity"]["native_sha256"] != rows["south-containing"]["identity"]["native_sha256"]:
        raise ValueError("The geographic offers changed the receiver packet")
    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == "DS30-0016" and r["authority_eligible"]]
    truth["DS30-0016"] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    results = {}
    for case, row in rows.items():
        base = controls[case]["complete"]
        identity = row["identity"]
        schedule = identity["selection"]
        scores = section(row["arms"], truth[case], base["arms"])
        full_acq = identity["ledger"]["acquisition_cpu_s"]
        other_acq = full_acq - identity["all_native_cpu_s"]
        totals = schedule["full_call_cpu_s_by_slot"]
        floor = other_acq + totals["full"] + schedule["charged_selection_cpu_s"] + row["cpu_s"]
        target = (full_acq + base["cpu_s"]) / 2
        arm_deltas = [scores["arms"][arm]["delta_error_km"] for arm in ARMS]
        screen = (row["status"] == "ok" and all(d is not None and d <= .25 for d in arm_deltas)
                  if case != "south-far" else checked_exterior(row))
        results[case] = dict(scores=scores, passed=screen, status=row["status"], reason=row["reason"],
                             baseline_status=base["status"], counts=schedule["counts"], selected=schedule["returned"],
                             owners=owner_changes(base, row), solver_cpu_s=row["cpu_s"], solver_elapsed_s=row["elapsed_s"],
                             baseline_solver_cpu_s=base["cpu_s"], recorded_full_acquisition_cpu_s=full_acq,
                             grid_points=row.get("grid_points"), route=row["attempts"][0]["decision"],
                             contract_exterior=checked_exterior(row), outside_native_cpu_s=other_acq,
                             full_anchor_native_cpu_s=totals["full"], primary_slot_original_native_cpu_s=totals["primary"],
                             selector_cpu_s=schedule["charged_selection_cpu_s"], zero_primary_floor_cpu_s=floor,
                             half_complete_acq_and_solve_cpu_s=target, short_call_allowance_cpu_s=target-floor)
    write(summary, dict(cases=results, controls_sha256=CONTROL_SHA,
                        receipts={case: sha256(path.read_bytes()).hexdigest() for case, path in paths.items()}))
    with archive.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(rows, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    runner = action.add_parser("run")
    runner.add_argument("case", choices=CASES)
    runner.add_argument("output", type=Path)
    scoring = action.add_parser("score")
    for name in ("directory", "summary", "archive"):
        scoring.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.action == "run":
        fit(args.case, "control", args.output, load_saved_inputs=prepare, single_attempt=True)
    else:
        score(args.directory, args.summary, args.archive)
