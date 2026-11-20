"""Frozen open-loop causal epoch hints into the full saved-IQ fractional GLRT."""

import argparse
import gzip
import json
from collections import defaultdict
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import hinted_glrt, iq_stream
from . import ordinary_front_eval, wide_regional_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import BULK, _from_native, _load_case, _probe, _sha, compare_probes

HERE = ROOT / "reports/2026_11_19_receiver_screening/receiver-core"
REPORT = HERE / "hinted-glrt"
PROPOSER = HERE / "causal-track-scout"
CASES = {"DS26-0237": "lower", "DS29-0174": "upper"}
LIMIT = 8
PREFIX_MAX = 48 * iq_stream.MIB
REPETITIONS = 3
MODES = ("stock", "off", "causal", "sham")


def sham(case, visit, receiver):
    key = f"hinted-glrt-sham-v1:{case}:{visit}:{receiver}".encode()
    return int.from_bytes(sha256(key).digest()[:8], "big") % hinted_glrt.FRAME


def checked_json(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"binding changed: {path}")
    return json.loads(raw)


def proposals():
    lock_path = PROPOSER / "prediction-lock.json"
    trace_path = PROPOSER / "proposals.jsonl.gz"
    lock = json.loads(lock_path.read_bytes())
    raw = trace_path.read_bytes()
    if (
        sha256(raw).hexdigest() != lock["files"][trace_path.name]
        or _sha(PROPOSER / "source-lock.json") != lock["source_lock_sha256"]
    ):
        raise ValueError("causal proposal receipt differs from the independent seal")
    index = defaultdict(dict)
    total = defaultdict(int)
    for row in map(json.loads, gzip.decompress(raw).splitlines()):
        case, visit, receiver = (row[k] for k in ("case", "visit", "receiver_id"))
        if case not in CASES or not row["centers"]:
            continue
        total[case] += 1
        key = visit, receiver
        if key in index[case] or any(
            type(x) is not int or not 0 <= x < hinted_glrt.FRAME for x in row["centers"]
        ):
            raise ValueError("invalid or duplicate causal proposal")
        index[case][key] = (row["counter"], row["channel"], row["centers"][0])
    return index, total, dict(proposal_sha256=sha256(raw).hexdigest(), lock_sha256=_sha(lock_path))


def select(case, hints):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    out, examined = [], []
    policy = FastScanPolicyV2()
    previous_visit = -1
    total_index_bytes = 0
    for segment, locator in enumerate(case["recording"]["segments"][:14]):
        path = BULK / locator["path"]
        manifest = iq_stream._read_prefix(path, 65537)
        if len(manifest) > 65536 or sha256(manifest).hexdigest() != locator["sha256"]:
            raise ValueError("IQ manifest differs from the frozen raw roster")
        manifest = json.loads(manifest)
        targets = {item["target_id"]: item for item in manifest["configuration"]["targets"]}
        receivers = tuple(manifest["receiver_ids"])
        for chunk in manifest["chunks"]:
            size = chunk["index_bytes"]
            total_index_bytes += size
            if size > iq_stream.MIB or total_index_bytes > 32 * iq_stream.MIB:
                raise ValueError("raw index metadata exceeded the prescribed bound")
            index = iq_stream._read_prefix(path.parent / chunk["index_relative_path"], size + 1)
            if len(index) != size or iq_stream._digest(index) != chunk["index_sha256"]:
                raise ValueError("raw index digest changed")
            prefix = 0
            for meta in map(json.loads, index.splitlines()):
                prefix += meta["payload_bytes"]
                acq = meta["acquisition"]
                visit = acq["global_visit"]
                if visit <= previous_visit:
                    raise ValueError("raw metadata must be in chronological visit order")
                previous_visit = visit
                proposal = [hints.get((visit, rx)) for rx in receivers]
                if not any(proposal):
                    continue
                target = targets[meta["target_id"]]
                counter, channel = acq.get("sample_start"), target["channel"]
                chosen = [p[2] if p and p[:2] == (counter, channel) else None for p in proposal]
                record = dict(
                    case=case["id"],
                    segment=segment,
                    sequence=meta["sequence"],
                    visit=visit,
                    receiver_ids=receivers,
                    channel=channel,
                    counter=counter,
                    iq_sha256=meta["iq_sha256"],
                    index_sha256=chunk["index_sha256"],
                    manifest_sha256=locator["sha256"],
                    raw_prefix_bytes=prefix,
                    causal=chosen,
                    sham=[
                        sham(case["id"], visit, rx) if h is not None else None
                        for rx, h in zip(receivers, chosen, strict=True)
                    ],
                )
                shape = SimpleNamespace(shape=(meta["sample_count"], meta["receiver_count"], 2))
                window = iq_stream.IQWindow(
                    meta["sequence"],
                    shape,
                    receivers,
                    manifest["sample_rate_hz"],
                    acq,
                    meta["target_id"],
                    target,
                    meta["iq_sha256"],
                )
                validity = analyze_window(
                    window,
                    receivers,
                    None,
                    policy,
                    detector=lambda _w, ids: tuple(
                        FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids
                    ),
                )
                if not any(h is not None for h in chosen):
                    reason = "proposal did not match raw counter and channel"
                elif validity.status != "processed" or receivers != (0, 1):
                    reason = "raw window fails the original dual-receiver policy"
                elif prefix > PREFIX_MAX:
                    reason = "raw chunk prefix exceeds the 48 MiB replay cap"
                else:
                    reason = "selected"
                    out.append(record)
                examined.append(dict(record, disposition=reason))
                if len(out) == LIMIT:
                    return out, examined, total_index_bytes
    return out, examined, total_index_bytes


def sources():
    from leo.analysis.starlink import native_short_window
    from leo.scanner import fast_scan_analysis

    paths = (
        Path(__file__),
        Path(hinted_glrt.__file__),
        hinted_glrt.HEADER,
        Path(iq_stream.__file__),
        Path(native_short_window.__file__),
        Path(wide_regional_eval.__file__),
        Path(ordinary_front_eval.__file__),
        Path(fast_scan_analysis.__file__),
        REPORT / "PROTOCOL.md",
    )
    return {str(p): _sha(p) for p in paths}


def freeze(work):
    prior, totals, authority = proposals()
    roster = {}
    for ident in CASES:
        case = _load_case(ident)
        kept, examined, index_bytes = select(case, prior[ident])
        roster[ident] = dict(
            selected=kept,
            examined=examined,
            index_bytes=index_bytes,
            positive_proposal_rows_in_case=totals[ident],
            archive_sha256=case["native"]["sha256"],
        )
    spec = dict(
        cases=roster,
        sources=sources(),
        proposal=authority,
        build_sha256=_sha(work / "build-lock.json"),
    )
    save_json(work / "input-lock.json", spec)


def authenticated(work):
    plan = json.loads((work / "input-lock.json").read_bytes())
    if sources() != plan["sources"] or _sha(work / "build-lock.json") != plan["build_sha256"]:
        raise ValueError("the prereplay plan or bound build changed")
    library = json.loads((work / "build-lock.json").read_bytes())
    if any(_sha(Path(p)) != library["library_sha256"][key] for key, p in library["paths"].items()):
        raise ValueError("detector libraries changed")
    return plan, library["paths"]


def bound(stack, libraries, edge):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    templates = wide_regional_eval.templates(10_000_000, edge)
    ports = [
        stack.enter_context(
            NativeShortWindow(
                libraries[k], *templates, sample_rate_hz=10_000_000, fractional_epoch=True
            )
        )
        for k in ("stock", "hinted")
    ]
    return ports[0], hinted_glrt.HintedCall(ports[1])


def measure(samples, stock, hinted, hints, order, reps=REPETITIONS):
    payloads, traces = {}, {}
    timings = defaultdict(list)
    for turn in range(reps):
        shift = (order + turn) % len(MODES)
        modes = MODES[shift:] + MODES[:shift]
        for mode in modes:
            cpu, wall = process_time_ns(), perf_counter_ns()
            if mode == "stock":
                observed, support = stock.analyze(samples, include_timings=True), None
            else:
                observed, support = hinted(samples, hints.get(mode, (None, None)), timings=True)
            run_wall, run_cpu = perf_counter_ns() - wall, process_time_ns() - cpu
            timings[mode].append(
                dict(
                    cpu_ns=run_cpu,
                    wall_ns=run_wall,
                    detector_ms=observed["detector_cpu_ms"],
                    rows=[r["timings_ms"] for r in observed["rows"]],
                )
            )
            science = ordinary_front_eval._payload(observed)
            if encoded(science) != encoded(
                payloads.setdefault(mode, science)
            ) or support != traces.setdefault(mode, support):
                raise ValueError("same-IQ stable replay violated")
    if encoded(payloads["stock"]) != encoded(payloads["off"]):
        raise ValueError("absent hints changed an original public result")
    for mode in ("causal", "sham"):
        for before, after in zip(traces["off"], traces[mode], strict=True):
            old, new = before["ordinary"], after["selected"]
            if (
                old != after["ordinary"]
                or len(old) != len(new)
                or old[:3] != new[:3]
                or len(new) > 4
            ):
                raise ValueError(
                    "hint changed stock scout decisions or increased its center budget"
                )
    return dict(payloads=payloads, traces=traces, timings=dict(timings))


def load_selected(case, row):
    locator = case["recording"]["segments"][row["segment"]]
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", PREFIX_MAX):
        (window,) = iq_stream.load_windows(
            dict(
                recording_path=str(BULK / locator["path"]),
                recording_sha256="sha256:" + locator["sha256"],
            ),
            [row["sequence"]],
        )
    if (
        window.iq_sha256 != row["iq_sha256"]
        or window.acquisition["sample_start"] != row["counter"]
        or window.acquisition["global_visit"] != row["visit"]
        or window.target["channel"] != row["channel"]
        or list(window.receiver_ids) != row["receiver_ids"]
        or locator["sha256"] != row["manifest_sha256"]
    ):
        raise ValueError("selected raw input differs from the immutable measurement plan")
    return window


def run(work, ident):
    plan, libs = authenticated(work)
    case = _load_case(ident)
    output = []
    with ExitStack() as stack:
        stock, hinted = bound(stack, libs, CASES[ident])
        for index, row in enumerate(plan["cases"][ident]["selected"]):
            try:
                w = load_selected(case, row)
            except iq_stream.IQReadError as error:
                output.append(dict(row, status="unavailable", reason=str(error)))
                continue
            result = measure(w.samples, stock, hinted, row, index)
            output.append(
                dict(
                    row,
                    result=result,
                    status="processed",
                    probes={
                        mode: [
                            _probe(
                                w,
                                rx,
                                (_from_native(j, c) for j, c in enumerate(lane["candidates"])),
                            )
                            for rx, lane in zip(w.receiver_ids, payload["rows"], strict=True)
                        ]
                        for mode, payload in result["payloads"].items()
                    },
                )
            )
            print(ident, row["visit"], row["causal"], flush=True)
    write(work / f"{ident}.json.gz", gzip.compress(encoded(output), mtime=0))


def controls(work):
    _, libs = authenticated(work)
    results = {}
    for k, edge in enumerate(CASES.values()):
        sign = 1 if edge == "lower" else -1
        geometry = wide_regional_eval.synthetic(10_000_000, edge)
        plants = ((735, sign * 688_125, 640),)
        paired = {
            "known_epoch": _test_signal(geometry, plants, 80293),
            "noise": _test_signal(geometry, (), 80212),
        }
        with ExitStack() as stack:
            stock, hinted = bound(stack, libs, edge)
            for name, window in paired.items():
                hints = {"causal": (735, 735), "sham": (6882, 6882)}
                result = measure(window.samples, stock, hinted, hints, k, reps=1)
                positives = {
                    mode: ordinary_front_eval.positive(p) for mode, p in result["payloads"].items()
                }
                results[f"{edge}:{name}"] = dict(
                    scope="known-epoch synthetic or noise only",
                    input_sha256=window.iq_sha256,
                    plants=plants if name == "known_epoch" else (),
                    positives=positives,
                    complete=result,
                )
    write(work / "controls.json.gz", gzip.compress(encoded(results), mtime=0))


def scoring(work):
    plan, _ = authenticated(work)
    result = {}
    for ident in CASES:
        case = _load_case(ident)
        source = checked_json(BULK / case["native"]["path"], plan["cases"][ident]["archive_sha256"])
        rows = json.loads(gzip.decompress((work / f"{ident}.json.gz").read_bytes()))
        selected = plan["cases"][ident]["selected"]
        if any(
            {k: row[k] for k in selection} != selection
            for row, selection in zip(rows, selected, strict=True)
        ):
            raise ValueError("prediction roster changed before scoring")
        visits = {row["visit"] for row in rows}
        archive = {
            (x["visit_index"], x["receiver_id"]): x
            for x in source["source"]["probes"]
            if x["visit_index"] in visits
        }
        evidence, times = [], defaultdict(list)
        for row in rows:
            if row["status"] != "processed":
                continue
            for mode, t in row["result"]["timings"].items():
                times[mode].extend(ti["detector_ms"] for ti in t)
            for index, receiver in enumerate(row["receiver_ids"]):
                probes = {m: values[index] for m, values in row["probes"].items() if m != "off"}
                evidence.append(
                    dict(
                        visit=row["visit"],
                        receiver=receiver,
                        channel=row["channel"],
                        hint=row["causal"][index],
                        rehearsal=row["sham"][index],
                        traces={
                            m: t[index] for m, t in row["result"]["traces"].items() if t is not None
                        },
                        against_archive={
                            m: compare_probes(archive[row["visit"], receiver], p, 10_000_000)
                            for m, p in probes.items()
                        },
                        against_wide={
                            m: compare_probes(probes["stock"], p, 10_000_000)
                            for m, p in probes.items()
                            if m != "stock"
                        },
                    )
                )
        result[ident] = dict(
            selected=len(rows),
            processed=sum(row["status"] == "processed" for row in rows),
            lanes=evidence,
            detector_median_ms={m: median(t) for m, t in times.items()},
            worker_trace_sha256=_sha(work / f"{ident}.json.gz"),
        )
    save_json(work / "summary.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("freeze", "controls", "score", *CASES))
    cli.add_argument("work", type=Path)
    args = cli.parse_args()
    home = local_output(args.work)
    if args.action == "freeze":
        if (home / "input-lock.json").exists():
            raise FileExistsError(home / "input-lock.json")
        freeze(home)
    elif args.action == "controls":
        controls(home)
    elif args.action == "score":
        scoring(home)
    else:
        run(home, args.action)
