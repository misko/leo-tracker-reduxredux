"""Replay one stereo visit and two opposite singleton visits per paid quintet."""

import argparse
from collections import Counter, defaultdict
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from aperture_trial import read, write
from full_family_amortized_trial import run as run_solver
from paid_certified_trial import GRAPH, PAIRED_FIELDS, actual_exterior, check_binding, sealed
from paid_graph_trial import prepare_paid
from sparse_consensus_trial import CASES, bound_inputs


HERE = Path(__file__).resolve().parent
MODES = ("complete", "primary", "inverted")


def slots(rows, *, inverted):
    streams = defaultdict(list)
    keys = ("channel", "actual_rf_hz", "edge", "visit_index", "valid_start_counter")
    visits = set()
    for index, (left, right) in enumerate(zip(rows[::2], rows[1::2], strict=True)):
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1)
                or any(left[k] != right[k] for k in keys) or left["visit_index"] in visits):
            raise ValueError("Expected original paired stereo chronology")
        visits.add(left["visit_index"])
        stream = streams[tuple(left[k] for k in keys[:3])]
        counter = left["valid_start_counter"]
        if stream and counter <= stream[-1][0]:
            raise ValueError("An RF stream is not in original counter order")
        stream.append((counter, index))

    paid, metadata = set(), []
    for ordinal, (key, stream) in enumerate(sorted(streams.items())):
        count, tail = divmod(len(stream), 5)
        for group in range(count):
            base = 5 * group
            first, middle, last = (stream[base + shift][1] for shift in (0, 2, 4))
            receiver = (ordinal + group + int(inverted)) % 2
            paid.update((2 * first, 2 * first + 1, 2 * middle + receiver, 2 * last + 1 - receiver))
        metadata.append(dict(channel=key[0], rf_hz=key[1], edge=key[2], available_visits=len(stream),
                             complete_groups=count, unpaid_tail_visits=tail))
    return paid, metadata


def select(rows, clocks, *, inverted):
    from leo.contracts.digests import canonical_digest

    if len(rows) != len(clocks):
        raise ValueError("Every original native slot needs its charged call clock")
    paid, streams = slots(rows, inverted=inverted)
    peaks = [[] for _ in rows]
    paid_factors = 0
    visits = Counter()
    receiver_slots = Counter()
    for i in sorted(paid):
        row = rows[i]
        visits[row["visit_index"]] += 1
        receiver_slots[str(row["receiver_id"])] += 1
        eligible = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
        paid_factors += len(eligible)
        if eligible:
            peaks[i] = [max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))]
    masks = sorted((rows[i]["visit_index"], rows[i]["receiver_id"]) for i in paid)
    return peaks, dict(paid_lanes=len(paid), paid_visits=len(visits), stereo_visits=sum(n == 2 for n in visits.values()),
                       singleton_visits=sum(n == 1 for n in visits.values()), paid_lanes_by_receiver=receiver_slots,
                       paid_factors=paid_factors, mask=masks, mask_sha256=canonical_digest(masks), streams=streams,
                       paid_native_cpu_s=sum(clocks[i] for i in paid) / 1e9)


def prepare(case, mode):
    from leo.contracts.digests import canonical_digest

    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    reference = sealed("complete")[case]["complete"]["identity"]
    identity.update(native_sha256=canonical_digest(native), schedule_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                    schedule_protocol_sha256=sha256((HERE / "mixed-stereo-paid-protocol.md").read_bytes()).hexdigest())
    check_binding(identity, reference, "complete")
    identity.update(mode=mode, complete_native_sha256=identity["native_sha256"], available_lanes=len(rows),
                    all_native_cpu_s=sum(clocks) / 1e9)
    if mode != "complete":
        cpu = process_time()
        native, _, stats = prepare_paid(native, rows, clocks, identity, mode,
                                       select_paid=partial(select, inverted=mode == "inverted"))
        identity.update(selection=stats, graph_parameters=GRAPH, native_sha256=canonical_digest(native))
        stats["charged_selection_cpu_s"] = process_time() - cpu
    return native, archive, offer, identity, mode != "complete"


def validate_pair(full, primary, inverted):
    authority = full["identity"]
    for receipt, mode in ((full, "complete"), (primary, "primary"), (inverted, "inverted")):
        branch = receipt["identity"]
        if not receipt["single_attempt"] or len(receipt["attempts"]) != 1 or branch["mode"] != mode:
            raise ValueError("The replay must run the requested one-pass mode")
        for key in (*PAIRED_FIELDS, "complete_native_sha256", "schedule_source_sha256", "schedule_protocol_sha256"):
            if branch[key] != authority[key]:
                raise ValueError("Complete and paid packets have different source binding")
    a, b = (r["identity"]["selection"] for r in (primary, inverted))
    if (a["paid_lanes"] != b["paid_lanes"] or 5 * a["paid_lanes"] > 2 * authority["available_lanes"]
            or sorted((v, 1-rx) for v, rx in a["mask"]) != [tuple(key) for key in b["mask"]]):
        raise ValueError("Complement changed visit, inversion or 40% call budget")


def account(row, full):
    identity, baseline = row["identity"], full["identity"]
    acquisition = baseline["ledger"]["acquisition_cpu_s"]
    native = baseline["all_native_cpu_s"]
    selection = identity.get("selection")
    charged_native = native if selection is None else selection["paid_native_cpu_s"]
    selector = 0. if selection is None else selection["charged_selection_cpu_s"]
    charged_acquisition = acquisition - native + charged_native + selector
    complete_total = acquisition + full["cpu_s"]
    return dict(native_cpu_s=charged_native, selection_cpu_s=selector, unchanged_acquisition_cpu_s=acquisition-native,
                projected_acquisition_cpu_s=charged_acquisition, projected_total_cpu_s=charged_acquisition + row["cpu_s"],
                native_ratio=charged_native/native, acquisition_ratio=charged_acquisition/acquisition,
                solve_cpu_ratio=row["cpu_s"]/full["cpu_s"], solve_elapsed_ratio=row["elapsed_s"]/full["elapsed_s"],
                projected_total_ratio=(charged_acquisition+row["cpu_s"])/complete_total)


def checked_exterior(row):
    return actual_exterior(row) and any(
        check["result"].get("evaluated") is True and check["result"].get("complete") is True
        and check["result"].get("would_withhold") is True for check in row["exterior_checks"]
    )


def score(directory, summary, full):
    from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
    from mixture_score import section
    from signed_0374_transfer import owner_changes

    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in MODES} for case in CASES}
    rows = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    for case, modes in rows.items():
        validate_pair(*(modes[mode] for mode in MODES))
        if case.startswith("south-") and any(row["identity"]["native_sha256"] != rows["south-containing"][m]["identity"]["native_sha256"]
                                             for m, row in modes.items()):
            raise ValueError("The southern offer changed the receiver packet")
    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == "DS30-0016" and r["authority_eligible"]]
    truth["DS30-0016"] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    old = sealed("complete")
    outcomes = {}
    for case, modes in rows.items():
        baseline = modes["complete"]
        original = old[case]["complete"]
        contains = face_clearance_km(baseline["identity"]["offer"], truth[case]) >= 0
        modes_scored = {}
        for mode, row in modes.items():
            fit = section(row["arms"], truth[case], baseline["arms"])
            selected = row["identity"].get("selection")
            outcomes_scored = (row["status"] == "ok" and all(a["delta_error_km"] is not None and a["delta_error_km"] <= .25
                                                               for a in fit["arms"].values())) if contains else checked_exterior(row)
            decision = row["attempts"][0]
            modes_scored[mode] = dict(
                **{key: row.get(key) for key in ("status", "reason", "cpu_s", "elapsed_s", "associated", "grid_points")},
                quality_screen=outcomes_scored, direct_quality_screen=outcomes_scored and decision["decision"] != "fallback",
                graph=row["prepared"], cold_rank=[r["clocks"] for r in row["ranks"]],
                charges=account(row, baseline), selection=None if selected is None else {k: v for k, v in selected.items() if k != "mask"},
                exterior=row["exterior_checks"], clocks={k: v for k, v in decision.items() if k.endswith("_clocks")},
                route=decision["decision"], route_reason=decision.get("reason"), signed=decision.get("signed", {}).get("status"),
                owners_vs_complete=owner_changes(baseline, row), versus_complete=fit,
                versus_archived_signed=section(row["arms"], truth[case], original["result"]["arms"]))
        outcomes[case] = dict(contained=contains, **modes_scored)
    verification = dict(receipts={path.name: sha256(path.read_bytes()).hexdigest() for modes in paths.values() for path in modes.values()},
                        references={path.name: sha256(path.read_bytes()).hexdigest() for path in (PHYSICAL, SIMULATED)})
    write(summary, dict(cases=outcomes, verification=verification))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(runs=rows, scores=outcomes, verification=verification),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    run = actions.add_parser("run")
    run.add_argument("case", choices=CASES)
    run.add_argument("mode", choices=MODES)
    run.add_argument("output", type=Path)
    scoring = actions.add_parser("score")
    for arg in ("directory", "summary", "full"):
        scoring.add_argument(arg, type=Path)
    args = parser.parse_args()
    if args.action == "run":
        run_solver(args.case, "control", args.output, load_saved_inputs=partial(prepare, mode=args.mode), single_attempt=True)
    else:
        score(args.directory, args.summary, args.full)
