"""Test the negative-only rescue on sealed source inputs without position labels."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, process_time_ns

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import negative_rescue, selective_capture
from . import (
    exact_wide_iq_results,
    frontier_whole_replay_results,
    support_cross,
    support_cross_trial,
)
from .factor_cross import winner
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/negative-rescue"
PARENT = REPORT.with_name("whole-replay")
CASES = {"DS26-0168": 12, "DS29-0604": 13}
BRANCHES = ("control", "candidate")
METHOD = "negative_rescue"
DEFAULT_RAW = Path("/var/tmp/leo-frontier-whole-20261119/runs")
read = whole_iq.read


def packet(probe):
    i = winner(probe["candidates"])
    return None if i is None else probe["candidates"][i]


def raw_pair(folder, authority, request, context):
    payloads, branches, evidence = [], [], {}
    receiver = authority["receiver"]
    for role in BRANCHES:
        path = folder / role
        measured, plan = (read(path / file) for file in ("raw.json", "plan.json"))
        detector = authority["detectors"][role]
        native = whole_iq.checked(path / "recording/native.json", measured["native_sha256"])
        document = read(native)
        rebound = whole_iq.checked(path / "recording/request.json", measured["request_sha256"])
        verify_request(read(rebound), request, native_path=native, native_sha256=_sha(native))
        if (
            plan["detector_sha256"] != detector["sha256"]
            or document["provenance"]["detector_sha256"] != "sha256:" + detector["sha256"]
            or plan["capture_era_request"] != context["request_sha256"]
            or plan["receiver"] != receiver
            or plan["receiver_files"] != authority["receiver_files"]
            or plan["cpus"] != context["cpus"]
        ):
            raise ValueError("raw parent is not the prospectively matched detector/receiver")
        whole_iq.checked(Path(detector["path"]), detector["sha256"])
        payloads.append(document)
        branches.append(exact_wide_iq_results.detector_rows(path))
        files = (
            "raw.json",
            "plan.json",
            "recording/replayed-0.jsonl",
            "recording/replayed-1.jsonl",
            "recording/replayed-0.log",
            "recording/replayed-1.log",
            "recording/request.json",
        )
        evidence[role] = dict(
            native_sha256=_sha(native),
            detector_sha256=detector["sha256"],
            files={name: _sha(path / name) for name in files},
        )
    return payloads, branches, evidence


def compare_raw(payloads, branches, folder):
    original, differential = branches
    telemetry = [dict(row, status="processed") for row in differential[1]]
    frontier_whole_replay_results.scout_trace(folder / "candidate", telemetry)
    clocks = [dict((r["visit"], r) for r in items) for items in (original[1], telemetry)]
    source_rows = [dict(selective_capture.visit_pairs(d["source"]["probes"])) for d in payloads]
    counts = Counter()
    times = []
    for orig, new in zip(original[0], differential[0], strict=True):
        visit = orig["visit"]
        if {k: v for k, v in orig.items() if k != "probes"} != {
            k: v for k, v in new.items() if k != "probes"
        }:
            raise ValueError("raw IQ, clocks, routing, or visit status differs between detectors")
        counts["visits"] += 1
        if orig["status"] == "invalid_capture":
            counts["invalid"] += 1
            continue
        counts["valid"] += 1
        if any(
            tuple(row["probes"]) != members[visit]
            for row, members in zip((orig, new), source_rows, strict=True)
        ):
            raise ValueError("authentic raw detector rows differ from their native packets")
        stock_clock, difference = (r[visit] for r in clocks)
        hint, trace = (difference["differential"][k] for k in ("hints", "changed"))
        for rx, (a, b) in enumerate(zip(orig["probes"], new["probes"], strict=True)):
            counts["unchanged_without_replacement"] += not trace[rx]
            if not trace[rx] and a != b:
                raise ValueError("stateless equivalence failed on a receiver without a replacement")
            if hint[rx] is None:
                counts["unhinted_exact"] += 1
                counts["unhinted_exact_with_peer_hint"] += hint[1 - rx] is not None
        times.append(
            dict(
                visit=visit,
                second_call=negative_rescue.misses(orig["probes"]),
                stock_cpu_s=stock_clock["cpu_s"],
                stock_wall_s=stock_clock["wall_s"],
                differential_cpu_s=difference["cpu_s"],
                differential_wall_s=difference["wall_s"],
            )
        )
    if len(times) != len(source_rows[0]) or len(times) != len(source_rows[1]):
        raise ValueError("incomplete joint whole-IQ support")
    return dict(counts), times


def combine(stock, differential):
    selective_capture.same_support(stock, differential)
    roster = support_cross.join(stock, differential)
    counts = Counter(roster)
    a, b = (d["source"]["probes"] for d in (stock, differential))
    start = process_time_ns()
    fused = [negative_rescue.select(x, y) for x, y in zip(a, b, strict=True)]
    selector_cpu_s = (process_time_ns() - start) / 1e9
    changed = []
    for original, new, selected, tag in zip(a, b, fused, roster, strict=True):
        if tag == "11" and packet(original) != packet(new):
            counts["changed_positive_winner_preserved"] += 1
        if tag == "01":
            counts["rescued"] += 1
            changed.append(
                dict(
                    visit=selected["visit_index"],
                    receiver=selected["receiver_id"],
                    counter=selected["valid_start_counter"],
                    cfo_hz=packet(selected)["fractional_tracking_cfo_hz"],
                )
            )
        if selected != (new if tag == "01" else original):
            raise ValueError("stock-positive or both-negative packet did not stay exact")
    return fused, dict(counts), changed, selector_cpu_s


def stage(work, raw, ident, authority):
    case, parent = whole_iq.binding(ident)
    context = authority["cases"][ident]
    if (
        context["request_sha256"] != case["request"]["sha256"]
        or context["catalog_sha256"] != case["catalog"]["sha256"]
        or context["tile"]["center"] != parent["job"]["search_center"]
    ):
        raise ValueError("whole-IQ parent used different request, catalogue or region")
    inputs, raw_rows, pins = raw_pair(raw / ident, authority, parent, context)
    stock, differential = inputs
    rows, counts, changed, selector = combine(stock, differential)
    raw_counts, timing = compare_raw(inputs, raw_rows, raw / ident)
    treatment = dict(
        id=ident, packets=counts, raw=raw_counts, gain=changed, selector_cpu_s=selector
    )
    lineage = whole_iq.recording.digest(["negative-rescue/v1", pins])
    document = dict(
        stock, source=dict(stock["source"], probes=rows, analysis_manifest_sha256=lineage)
    )
    document["provenance"] = dict(stock["provenance"], run_id="negative-rescue-" + lineage[7:30])
    document["provenance"].pop("detector_sha256")
    root = work / ident / "rescue"
    folder = root / "recording"
    folder.mkdir(parents=True, exist_ok=False)
    native, request = folder / "native.json", folder / "request.json"
    write(native, encoded(document) + b"\n")
    bound = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(read(request), parent, native_path=native, native_sha256=bound)
    save_json(root / "plan.json", dict(receiver=authority["receiver"]))
    save_json(root / "raw.json", dict(native_sha256=bound, request_sha256=_sha(request)))
    return (
        dict(
            id=ident,
            condition="rescue",
            method=METHOD,
            cpu=CASES[ident],
            mode="matched-tile",
            native_sha256=bound.removeprefix("sha256:"),
            prepared_request_sha256=_sha(request),
            stock_native_sha256=pins["control"]["native_sha256"],
            differential_native_sha256=pins["candidate"]["native_sha256"],
            paired_capture_sha256=context["capture_native_sha256"],
            catalog_sha256=context["catalog_sha256"],
            original_request_sha256=context["request_sha256"],
            tile=context["tile"],
            admitted_visits=raw_counts["valid"],
            original_probes=len(rows),
            positive_probes=sum(map(negative_rescue.positive, rows)),
            positive_candidates=sum(
                c[negative_rescue.GATE] is True for p in rows for c in p["candidates"]
            ),
            raw_parents=pins,
        ),
        treatment,
        [dict(id=ident, **row) for row in timing],
    )


def run(work, raw):
    if (REPORT / "plan.json").exists():
        raise FileExistsError("the sealed rescue trial already exists")
    work.mkdir(exist_ok=False)
    path = whole_iq.checked(
        raw / "source-lock.json", (raw / "source-lock.sha256").read_text().strip()
    )
    authority = read(path)
    if (
        set(authority["cases"]) != set(CASES)
        or authority["activation"]["policy"] != "unprivileged-differential"
    ):
        raise ValueError("the two whole-IQ stock/differential inputs are required")
    if whole_iq.receiver_identity(Path(authority["receiver"])) != authority["receiver_files"]:
        raise ValueError("installed solver files differ from the whole-IQ comparator")
    rows, audit, timing = [], [], []
    for ident in CASES:
        row, matched, measurements = stage(work, raw, ident, authority)
        rows.append(row)
        audit.append(matched)
        timing.extend(measurements)
    save_json(REPORT / "probe-audit.json", audit)
    write(REPORT / "raw-clock-ledger.jsonl.gz", compressed_rows(timing))
    sources = [
        Path(__file__),
        Path(negative_rescue.__file__),
        Path(exact_wide_iq_results.__file__),
        Path(frontier_whole_replay_results.__file__),
        Path(support_cross_trial.__file__),
        REPORT / "PROTOCOL.md",
    ]
    save_json(
        REPORT / "plan.json",
        dict(
            scheduled=rows,
            parent_source_lock_sha256=_sha(path),
            receiver=authority["receiver"],
            receiver_files=authority["receiver_files"],
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            service_cap_s=support_cross_trial.LIMIT,
        ),
    )
    print("locked", [(r["id"], r["packets"], r["raw"]) for r in audit], flush=True)
    start = monotonic()
    with ThreadPoolExecutor(2) as pool:
        attempt = list(pool.map(lambda row: support_cross_trial.service(work, row), rows))
    write(REPORT / "predictions.jsonl.gz", compressed_rows(attempt))
    files = ("plan.json", "predictions.jsonl.gz", "probe-audit.json", "raw-clock-ledger.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            attempted=len(attempt),
            wall_s=monotonic() - start,
            files={f: _sha(REPORT / f) for f in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=local_output, default=DEFAULT_RAW)
    args = parser.parse_args()
    run(args.work, args.raw)
