"""Run reviewed shortened timing and ordinary guarded acquisition on one signed member."""

import argparse
from contextlib import nullcontext
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from all_visit_timing import LAYOUT, PRIOR, activate, checked, digest, read_pack


ORDERS = (("ordinary", "shorter"), ("shorter", "ordinary"))
MIN_NATIVE_REDUCTION = .12


def read(path):
    return json.loads(path.read_bytes())


def write(path, doc):
    with path.open("x") as stream:
        json.dump(doc, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def minimum(retained, count):
    return retained * 6 >= count * 5 and count > 0


def prior_science(path):
    raw = gzip.decompress(path.read_bytes())
    if sha256(raw).hexdigest() != PRIOR:
        raise ValueError("Original timing-lag receipt changed")
    prior = json.loads(raw)
    variants = ("one_four", "two_four", "two_eight")
    scores = {}
    for name in variants:
        groups = {}
        for case in ("dense", "weak"):
            for lane in (0, 1):
                sample = [r for r in prior[case]["rows"] if r["kind"] == "short" and r["lane"] == lane]
                occupied = sum(bool(r["reference"]) for r in sample)
                groups[f"{case}-{lane}"] = dict(
                    positives=occupied, retained=occupied - sum(r["arms"][0][name]["lost_selection"] for r in sample))
        training = prior["builds"]["short"]["training"][name]
        scores[name] = dict(groups=groups, training=training, dense_short_cpu=prior["dense"]["summary"][name + "/short"]["cpu"],
                            eligible=training == 12 and all(minimum(g["retained"], g["positives"]) for g in groups.values()))
    chosen = min((name for name in scores if scores[name]["eligible"]), key=lambda name: scores[name]["dense_short_cpu"])
    if chosen != "two_four":
        raise ValueError("Frozen shortest prior candidate differs")
    return dict(chosen=chosen, scores=scores)


def signed_match(a, b):
    fields = ("integer_epoch_sample", "fractional_epoch_offset_samples", "fractional_tracking_cfo_hz")
    ea, da, fa = (a[key] for key in fields)
    eb, db, fb = (b[key] for key in fields)
    p = 40_000 / 3
    return (a["candidate_rank"] == b["candidate_rank"] and abs((ea + da - eb - db + p/2) % p - p/2) <= 2
            and abs(fa - fb) <= 250 and a["passed_fractional_margin_gate"] and b["passed_fractional_margin_gate"])


def compare(ref, test, anchors):
    result = {}
    for a, b in zip(ref, test, strict=True):
        if {k:v for k,v in a.items() if k != "candidates"} != {k:v for k,v in b.items() if k != "candidates"}:
            raise ValueError("The scans do not share the signed capture and probe order")
        anchorscope = a["visit_index"] in anchors
        if len(a["candidates"]) > 1 or len(b["candidates"]) > 1:
            raise ValueError("Expected one selected factor per signed lane")
        mode = "full" if anchorscope else "short"
        row = result.setdefault(f"{mode}-{a['receiver_id']}", dict(lanes=0, positives=0, candidate=0,
                                                                    retained=0, missing=0, extra=0, changed=0, both_empty=0))
        before = next(iter(a["candidates"]), None)
        after = next(iter(b["candidates"]), None)
        retained = before is not None and after is not None and signed_match(before, after)
        row["lanes"] += 1
        row["positives"] += before is not None
        row["candidate"] += after is not None
        row["retained"] += retained
        row["missing"] += before is not None and not retained
        row["extra"] += after is not None and not retained
        row["changed"] += before != after
        row["both_empty"] += before is None and after is None
    return result


def matched(reference, candidate, ordinary, bounded):
    from anchor_exposure import enroll

    if (reference["prefix_inventory"] != candidate["prefix_inventory"] or reference["iq"] != candidate["iq"]
            or reference["acquisition"]["recording_authority"] != candidate["acquisition"]["recording_authority"]
            or reference["acquisition"]["issued"] != candidate["acquisition"]["issued"]
            or reference["opened"] != candidate["opened"] or ordinary["clock_anchor"] != bounded["clock_anchor"]
            or ordinary["provenance"]["excluded_windows"] != bounded["provenance"]["excluded_windows"]):
        raise ValueError("The receiver changed its input, clocks or admitted signed source opportunities")
    a, b = (arm["acquisition"]["native"] for arm in (reference, candidate))
    if any(a[key] != b[key] for key in ("rule", "visits", "streams", "native_calls")):
        raise ValueError("Both antennas must still receive every original scheduled call")
    anchors = {visit for visit, _, _, _, kind, _ in enroll(ordinary) if kind == "anchor"}
    raw = compare(reference["original_probes"], candidate["original_probes"], anchors)
    if any(row["changed"] for mode, row in raw.items() if mode.startswith("full")):
        raise ValueError("The alternate short object changed a full anchor or its cancellation winner")
    selected = compare(ordinary["source"]["probes"], bounded["source"]["probes"], anchors)
    recipe = candidate["recipe"]["short_timing_scout"]
    if any(recipe[key] != value for key, value in LAYOUT.items()):
        raise ValueError("Selected packet lost the shortened timing identity")
    return dict(before_cfo=raw, selected=selected,
                enough=all(minimum(row["retained"], row["positives"]) for mode, row in raw.items() if mode.startswith("short")),
                primary_cpu_ns=[a["native_cpu_ns"]["short_primary"], b["native_cpu_ns"]["short_primary"]],
                anchor_cpu_ns=[a["native_cpu_ns"]["full"], b["native_cpu_ns"]["full"]],
                correction=[dict(scope["held_choice"], paid_lanes=scope["paid"]) for scope in (reference, candidate)],
                correction_cpu_ns=[a["cfo_refinement"]["cpu_ns"], b["cfo_refinement"]["cpu_ns"]])


def worker(mode, output, pack, pin):
    from continued_cfo_first_0016 import worker as receiver

    with (activate(pack, pin) if mode == "shorter" else nullcontext()):
        receiver("guarded", output)


def run(root, pack, pin):
    from continued_cfo_first_0016 import mapped_files, resident
    from short_raw_diagnostic import measure

    if root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}:
        raise ValueError("Use a fresh tmpfs output in the shared CPU2 slot")
    pack_info, _ = read_pack(pack, pin)
    prior = prior_science(HERE / "measurements/short-timing-lags.json.gz")
    chunk, files = mapped_files()
    root.mkdir()
    before = resident(files)
    rows = []
    for repeat, order in enumerate(ORDERS):
        runs = {}
        for mode in order:
            work = root / f"{repeat}-{mode}"
            command = [sys.executable, "-B", str(Path(__file__)), str(work), str(pack), pin, "--worker", mode]
            clock = measure(command, dict(os.environ), work)
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
            runs[mode] = dict(clock=clock, scope=read(work / "scope-receipt.json"), native=read(work / "detections.json"))
        a, b = (runs[mode] for mode in ("ordinary", "shorter"))
        score = matched(a["scope"], b["scope"], a["native"], b["native"])
        score["reduction"] = 1 - score["primary_cpu_ns"][1] / score["primary_cpu_ns"][0]
        rows.append(dict(order=order, score=score, runs=runs))
    first, second = rows
    if any(first["runs"][mode]["scope"]["native_sha256"] != second["runs"][mode]["scope"]["native_sha256"]
           for mode in ORDERS[0]):
        raise ValueError("Repeat order changed the signed packet")
    reduction = median(row["score"]["reduction"] for row in rows)
    eligible = all(row["score"]["enough"] and row["score"]["reduction"] > 0 for row in rows) and reduction >= MIN_NATIVE_REDUCTION
    write(root / "result.json", dict(member=chunk, original=files, admitted_before=before, admitted_after=resident(files),
          pack=pack_info, pack_sha256=pin, prior=prior, pairs=rows, median_native_reduction=reduction, north_eligible=eligible,
          sources={name: digest(HERE / name) for name in ("all_visit_timing_trial.py", "all_visit_timing.py", "all-visit-timing-protocol.md")}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("pack", type=Path)
    cli.add_argument("pin")
    cli.add_argument("--worker", choices=ORDERS[0])
    args = cli.parse_args()
    if args.worker:
        worker(args.worker, args.root, args.pack, args.pin)
    else:
        run(args.root, args.pack, args.pin)
