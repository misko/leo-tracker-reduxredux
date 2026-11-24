"""Compare the registered guarded-full/sparse8 callback on two resident originals."""

import argparse
from collections import Counter
from contextlib import closing
import gzip
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace

import guarded_full_anchor as guarded
import mixed_aperture_receiver as mixed
from signed_peak_0163 import THREADS, STAGE as STAGE_0163, RELEASE, FULL, SPARSE, archived, checked, scopes


LIBRARY = Path("/dev/shm/leo-anchored-cfo-raw-pack01/full.so")
AUDITED_EXACT = Path("/dev/shm/leo-anchored-phase-results02/full-stock/receiver.so")
AUDITED_EXACT_PIN = "1dfe03a2205ef735d5bd15b85d1a11aa34a6f0be9f60ccc8b64ce5bb7ef9ffdb"
ROOT_0169 = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
STAGE_0169 = ROOT_0169 / "fast8-auto-20261116-022353-b914c97a-1-lower-segment-00000000"
SCOPE_0169 = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
PRIOR_0169 = Path("/dev/shm/leo-independent-8ms-0169-result02/measured8.json")
PRIOR_0169_PIN = "0c6055720b8f4d0a50c7e446165256f0a1431a6d9a7734358e7f2a41f0c12c19"
ORDERS = (("exact", "guarded"), ("guarded", "exact"))*2
SCORES = ("fractional_exact_score", "fractional_control_score", "fractional_margin")
LIMIT = 1e-8


def now():
    return process_time_ns(), perf_counter_ns()


def clock(start):
    return dict(cpu_ns=process_time_ns()-start[0], wall_ns=perf_counter_ns()-start[1])


def deny_backing(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        p = Path(os.fsdecode(args[0])).absolute()
        if (p.is_relative_to("/srv/bulk") or p.is_relative_to("/mnt/qnap01")
                or p.name.endswith(".ci16.zst") and p not in {root/"iq-000000.ci16.zst" for root in (STAGE_0163, STAGE_0169)}):
            raise PermissionError("Only these two enrolled original member copies may be opened")


def enrollment():
    docs = archived("first-member-0163-resume-acquisition.json.gz")
    book, _ = scopes(docs)
    frozen = docs["documents"]
    worker = frozen["integrated/worker.json"]["document"]
    source = json.loads(checked(ROOT_0169 / "scope.json", SCOPE_0169))
    prior = json.loads(checked(PRIOR_0169, PRIOR_0169_PIN))
    if Path(source["entry"]["path"]) != STAGE_0169:
        raise ValueError("Independent signed source path changed")
    return (
        ("DS30-0163", STAGE_0163, book["manifest_sha256"], book["member"], worker["iq"], worker["before_selection"],
         frozen["integrated/detections.json"]["document"]),
        ("DS30-0169", STAGE_0169, source["entry"]["manifest_digest"], source["member"], prior["iq"],
         prior["packet"]["source"]["probes"], prior["packet"]),
    )


def windows(stage, manifest, member, expected):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.short_window import ShortWindowReader

    started = now()
    if subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", stage], text=True).strip() != "tmpfs":
        raise ValueError("Expected only already resident originals")
    paths = [stage/name for name in ("manifest.json", member["index_relative_path"], member["payload_relative_path"])]
    if any(path.resolve(strict=True) != path for path in paths):
        raise ValueError("The staged original escaped the signed local path")
    checked(paths[0], manifest)
    reader = ShortWindowReader(stage)
    if (reader.manifest.chunks[0].model_dump(mode="json") != member or member["window_count"] != 64
            or member["first_sequence"] or reader.manifest.sample_rate_hz != 10_000_000
            or reader.manifest.receiver_ids != (0, 1)):
        raise ValueError("Original stereo member identity changed")
    targets = {r["target_id"]: r for r in reader.manifest.configuration["targets"]}
    history, ready = [], []
    for row in reader.windows(stop_sequence=64):
        index, samples = row.index, row.samples
        if index.sequence != len(history) or samples.flags.writeable:
            raise ValueError("Expected consecutive original immutable windows")
        history.append(index.iq_sha256)
        if valid_window_support(index.acquisition, 10_000_000, samples.shape, (0, 1), FastScanPolicyV2()):
            ready.append(SimpleNamespace(sequence=index.sequence, iq_sha256=index.iq_sha256, acquisition=index.acquisition,
                         target=targets[index.target_id], samples=samples, sample_rate_hz=10_000_000, receiver_ids=(0, 1)))
    if len(history) != 64 or history != expected or not ready:
        raise ValueError("Original decoded evidence differs from the previously verified first member")
    return ready, clock(started)


def schedule(windows):
    policy = mixed.StereoSchedule(full_coverage=True)
    return [policy.visit(w.target["edge"], w.target, w.acquisition)[1] for w in windows]


def callbacks(rows, mixer, asset):
    started = now()
    with mixer.detector("cancellation", asset.stem, binary=FULL, pilot=asset) as receive:
        setup = clock(started)
        started = now()
        probes = [p for window in rows for p in receive(window)]
        paid = clock(started)
    return probes, dict(setup=setup, callback=paid, receipt=mixer.receipt())


def compare_numbers(a, b, maximum):
    for name, x, y in zip(("exact", "rolled"), a, b, strict=True):
        delta = abs(x-y)
        if not math.isfinite(delta) or delta > LIMIT:
            raise ValueError("Native continuous scores exceed the previously frozen tolerance")
        maximum[name] = max(maximum[name], delta)


def compare_probes(stock, alternative, modes):
    changes, biggest = 0, Counter()
    for i, (first, second) in enumerate(zip(stock, alternative, strict=True)):
        if first == second:
            continue
        if modes[i//2] != "full" or {k:v for k,v in first.items() if k != "candidates"} != {k:v for k,v in second.items() if k != "candidates"}:
            raise ValueError("Short bytes or exact signed opportunity metadata changed")
        for a, b in zip(first["candidates"], second["candidates"], strict=True):
            if {k:v for k,v in a.items() if k not in SCORES} != {k:v for k,v in b.items() if k not in SCORES}:
                raise ValueError("The new anchor changed signed rank, phase, CFO or gate decisions")
            compare_numbers([a[k] for k in SCORES[:2]], [b[k] for k in SCORES[:2]], biggest)
            delta = abs(a[SCORES[-1]]-b[SCORES[-1]])
            if not math.isfinite(delta) or delta > LIMIT:
                raise ValueError("Selected margin change exceeds the frozen tolerance")
            biggest["margin"] = max(biggest["margin"], delta)
        changes += 1
    return dict(changed_continuous_lanes=changes, maxima=dict(biggest))


def anchor_trace(rows, modes, asset):
    import numpy as np
    from contextlib import ExitStack

    data = np.frombuffer(mixed.verified(asset, mixed.PILOT_SHA[asset.stem]), dtype="<f4")
    mixed.verified(AUDITED_EXACT, AUDITED_EXACT_PIN)
    with ExitStack() as stack:
        paths = [stack.enter_context(closing(mixed.NativePath(p, data, "full"))) for p in (FULL, AUDITED_EXACT, LIBRARY)]
        audit = [guarded.NativeAudit(path.native.lib) for path in paths[1:]]
        signed, maximum, audit_max, totals = [], Counter(), Counter(), Counter()
        for window, mode in zip(rows, modes, strict=True):
            if mode != "full":
                continue
            center = window.target["rf_center_hz"] - window.target["lnb_lo_hz"] - window.acquisition["actual_if_center_hz"]
            for lane in window.receiver_ids:
                original, exact, candidate = [path.run(window.samples, lane, center)[0] for path in paths]
                (_, first), (counts, second) = (a.drain(rows=True) for a in audit)
                if original != exact:
                    raise ValueError("Audited exact anchors do not reproduce the actual original full DSO")
                for a, b in zip(original, candidate, strict=True):
                    if a[:4] != b[:4]:
                        raise ValueError("Original ordered native alternative rank, phase or signed CFO changed")
                    compare_numbers(a[4:], b[4:], maximum)
                final = [{(r[0], r[2]):r for r in events} for events in (first, second)]
                if list(final[0]) != list(final[1]):
                    raise ValueError("The actual full verifier evaluated different scouts")
                for a, b in zip(final[0].values(), final[1].values(), strict=True):
                    if a[:5] != b[:5]:
                        raise ValueError("The pre-held full gate, integer/fractional flags or residual CFO changed")
                    compare_numbers(a[5:], b[5:], audit_max)
                totals.update(counts)
                totals.update(native_factors=len(original), rank_one=sum(r[0] == 1 for r in original), empty_lanes=not original,
                              completed_gate=sum(bool(r[1]&4) for r in final[0].values()),
                              failed_fractional_gate=sum(bool(r[1]&4) and not r[1]&2 for r in final[0].values()),
                              final_failed_integer_gate=sum(not r[1]&1 for r in final[0].values()))
                signed.append(dict(visit=window.sequence, counter=window.acquisition["sample_start"], lane=lane, center=center,
                                   iq_sha256=window.iq_sha256, exact=original, guarded=candidate,
                                   exact_verifier=first, guarded_verifier=second, guard_counters=counts))
    return dict(native_maxima=dict(maximum), verifier_maxima=dict(audit_max), counts=dict(totals), lanes=signed)


def member(fixture, root, original, short_pin):
    from continued_cfo_trial import rebinding
    from eight_ms_native_receiver import prepare

    label, directory, manifest, chunk, expected, reference, previous = fixture
    ready, paid_intake = windows(directory, manifest, chunk, expected)
    modes = schedule(ready)
    if len({w.target["edge"] for w in ready}) != 1:
        raise ValueError("Expected the fixed single-edge first member")
    asset = RELEASE / "assets" / (ready[0].target["edge"] + ".f32")
    runs, receipts, last_recipe = [], {}, None
    for order in ORDERS:
        clocks = {}
        for name in order:
            started = now()
            if name == "guarded":
                mixer, last_recipe = guarded.configure(SPARSE, short_pin, original, LIBRARY)
            else:
                mixer = mixed.MixedApertureDetector(SPARSE, short_pin, full_coverage=True)
            configuration = clock(started)
            probes, clocks[name] = callbacks(ready, mixer, asset)
            clocks[name]["configuration"] = configuration
            if receipts.setdefault(name, probes) != probes:
                raise ValueError("The same calibrated callback is not deterministic")
        runs.append(dict(order=order, measures=clocks))
    if receipts["exact"] != reference:
        raise ValueError("Exact current callback did not reproduce the enrolled original probe bytes")
    comparison = compare_probes(receipts["exact"], receipts["guarded"], modes)
    audited = anchor_trace(ready, modes, asset)
    recipe = {"exact": original, "guarded": last_recipe}
    session, inventory = (previous["source"][f] for f in ("session_id", "input_manifest_sha256"))
    held = {}
    for mode, probes in receipts.items():
        before = rebinding(previous, probes, recipe[mode])
        after, _, _, audit = prepare(before, recipe[mode], session, inventory, root/f"{label}-{mode}-held.json")
        held[mode] = dict(packet=after, witness=audit)
    a, b = (held[mode]["witness"] for mode in ("exact", "guarded"))
    if a["choice"]["route"] != b["choice"]["route"] or a["selected"] != b["selected"] or a["refinement_calls"] or b["refinement_calls"]:
        raise ValueError("The unchanged held selector made a different decision")
    final = [held[mode]["packet"]["source"]["probes"] for mode in ("exact", "guarded")]
    return dict(case=label, manifest_sha256=manifest, chunk=chunk, intake=paid_intake, native_clocks=runs,
                schedule=modes, signed_preheld=receipts, held=held, guarded_recipe=last_recipe,
                preheld_comparison=comparison, held_comparison=compare_probes(*final, modes), full_trace=audited)


def run(root):
    from full_short_run import SPARSE_EIGHT_MS_SHA, checked_recipe

    io = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15 or "prio 7" not in io or any(os.getenv(k) != "1" for k in THREADS):
        raise ValueError("The native physical measurement requires the shared low-priority slot")
    sys.addaudithook(deny_backing)
    root.mkdir(mode=0o700)
    original = checked_recipe(eight_ms=True, short_pin=SPARSE_EIGHT_MS_SHA)
    cases = [member(fixture, root, original, SPARSE_EIGHT_MS_SHA) for fixture in enrollment()]
    record = dict(cases=cases, order=ORDERS, cpu_affinity=[2], io_priority=io, original_backing_bytes=0,
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), audited_exact_sha256=AUDITED_EXACT_PIN)
    body = gzip.compress((json.dumps(record, sort_keys=True, indent=2, allow_nan=False)+"\n").encode(), mtime=0)
    (root/"result.json.gz").write_bytes(body)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
