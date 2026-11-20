"""Pair stock, fourth-center replacement, and union on frozen authentic sample windows."""

import argparse
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, write
from ..variants import center_union, hinted_glrt, iq_stream
from ..variants.differential_runtime_fft import FftScout
from . import (
    center_union_build,
    center_union_gate,
    differential_pilot_eval,
    differential_runtime_eval,
    hinted_glrt_trial,
    oracle_start,
    ordinary_front_eval,
)
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _from_native, _load_case, _probe, _sha, compare_probes
from .pilot_kernel_eval import _digest, _windows
from .wide_regional_eval import RATE
from .wide_regional_eval import synthetic as control_window

REPORT = center_union_gate.REPORT
MODES = ("stock", "replace", "union")
ADDITIONAL = ("DS26-0168", "DS29-0604")


def load(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def freeze(work):
    gate = whole_iq.read(REPORT / "feature-gate.json")
    for name, sha in gate["files"].items():
        whole_iq.checked(REPORT / name, sha)
    paths, _ = center_union_gate.release(work)
    capture = [
        dict(row, cohort=scope, edge=row["archive_probe"]["edge"])
        for scope, ident, row in differential_runtime_eval.locked_visits()
    ]
    if len(capture) != 32 or len({(r["case"], r["visit"]) for r in capture}) != len(capture):
        raise ValueError("complete independently locked differential panel is absent")
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
        for ident in ADDITIONAL:
            case = _load_case(ident)
            for segment in (4, 9):
                (window,) = _windows(case, segment, (8,))
                capture.append(
                    dict(
                        case=ident,
                        segment=segment,
                        sequence=8,
                        cohort="additional",
                        edge=window.target["edge"],
                        iq_sha256=window.iq_sha256,
                        visit=int(window.acquisition["global_visit"]),
                    )
                )
    files = (
        Path(__file__),
        REPORT / "feature-gate.json",
        Path(center_union.__file__),
        Path(differential_runtime_eval.__file__),
    )
    return dict(
        capture=capture,
        sha256={k: _sha(Path(v)) for k, v in paths.items()},
        paths=paths,
        inputs={str(p.relative_to(ROOT)): _sha(p) for p in files},
    )


def measure(sample, native, replace, union, scout, edge, *, index):
    signatures, traces = {}, {}
    times = {mode: [] for mode in MODES}
    for rep in range(3):
        offset = (index + rep) % len(MODES)
        for mode in MODES[offset:] + MODES[:offset]:
            wall, cpu = perf_counter_ns(), process_time_ns()
            if mode == "stock":
                out, hint_trace = native["stock"].analyze(sample, include_timings=True), None
                hints = None
            else:
                hints = tuple(v[0] if v else None for v, _ in scout(sample, edge))
                call = replace if mode == "replace" else union
                out, hint_trace = call(sample, hints, timings=True)
            wrapper_wall = (perf_counter_ns() - wall) / 1e6
            wrapper_cpu = (process_time_ns() - cpu) / 1e6
            payload = ordinary_front_eval._payload(out)
            trace = dict(values=hint_trace, rank_one=hints)
            if encoded(payload) != encoded(signatures.setdefault(mode, payload)) or (
                encoded(trace) != encoded(traces.setdefault(mode, trace))
            ):
                raise ValueError("repeat changed selected timing region or detector payload")
            times[mode].append(
                dict(
                    cpu_ms=wrapper_cpu,
                    wall_ms=wrapper_wall,
                    native_cpu_ms=out["detector_cpu_ms"],
                    coarse_cpu_ms=sum(r["timings_ms"]["coarse"] for r in out["rows"]),
                )
            )
    null, baseline = union(sample)
    if encoded(null) != encoded(signatures["stock"]):
        raise ValueError("null hint changed the stock detector payload")
    if traces["replace"]["rank_one"] != traces["union"]["rank_one"]:
        raise ValueError("placement policies received different independent FFTW hints")
    after = traces["union"]["values"]
    center_union_gate.preserved(baseline, after)
    for payload, row in zip(signatures["stock"]["rows"], baseline, strict=True):
        count = payload["retained_peak_count"]
        if count and row["retained_stock"] != count:
            raise ValueError("null-hint nominal top-K differs from the stock point budget")
    traces["stock"] = baseline
    return dict(payloads=signatures, traces=traces, timings=times)


def projections(payloads):
    out = {}
    for mode, doc in payloads.items():
        out[mode] = [
            dict(
                candidates=[
                    c
                    for idx, source in enumerate(row["candidates"])
                    if (c := _from_native(idx, source)) is not None
                ]
            )
            for row in doc["rows"]
        ]
    return out


def endpoints(data, projections, registered):
    keys = {}
    for mode, votes in projections.items():
        rows = data["payloads"][mode]["rows"]
        keys[mode] = [
            oracle_start.endpoints(target, votes[rx], rows[rx]) for rx, target in registered
        ]
    return keys


def account(data, registered):
    probes = projections(data["payloads"])
    comparison = {
        role: [
            compare_probes(a, b, RATE) for a, b in zip(probes["stock"], probes[role], strict=True)
        ]
        for role in ("replace", "union")
    }
    counts = {
        role: [sum(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in slate]
        for role, slate in probes.items()
    }
    return dict(
        data,
        gate_counts=counts,
        stock_gate_compared=comparison,
        target_results=endpoints(data, probes, registered),
        target_count=len(registered),
    )


def synthetic(edge):
    from . import factor_cross

    for name in differential_pilot_eval.CONTROLS:
        sample, plant = differential_pilot_eval.synthetic(edge, name)
        targets = [(plant["epoch"], plant["cfo_hz"])] if plant["plant"] else []
        yield name, sample, registered(targets, factor_cross)
    sign = 1 if edge == "lower" else -1
    pair = [(735, sign * 688_125, 640), (2291, sign * 480_000, 288)]
    sample = _test_signal(control_window(RATE, edge), pair, 59347).samples
    yield "two_family", sample, registered([p[:2] for p in pair], factor_cross)


def registered(tones, factor_cross):
    return [
        (
            rx,
            {
                "integer_epoch_sample": int(epoch),
                "fractional_epoch_offset_samples": 0.0,
                factor_cross.CFO: float(hz),
                factor_cross.MARGIN: 0.0,
            },
        )
        for epoch, hz in tones
        for rx in (0, 1)
    ]


def replay(edge, lock):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    outputs = []
    with ExitStack() as stack:
        native = center_union_gate.bind(stack, lock["paths"], edge)
        scout = stack.enter_context(FftScout(lock["paths"]["fftw"], edge))
        union = center_union.UnionCall(native["union"])
        replace = hinted_glrt.HintedCall(native["hinted"])
        policy = FastScanPolicyV2()
        args = (native, replace, union, scout, edge)
        for index, row in enumerate(r for r in lock["capture"] if r["edge"] == edge):
            case = _load_case(row["case"])
            if row["cohort"] == "additional":
                with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
                    (window,) = _windows(case, row["segment"], (row["sequence"],))
                targets = []
            else:
                window = hinted_glrt_trial.load_selected(case, row)
                targets = [(row["receiver"], row["target"])]
            if window.iq_sha256 != row["iq_sha256"] or window.target["edge"] != edge:
                raise ValueError("saved waveform differs from the frozen antenna and input bytes")
            status = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _, ids: tuple(
                    FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids
                ),
            ).status
            measured = {}
            if status == "processed":
                data = measure(window.samples, *args, index=index)
                projected = projections(data["payloads"])["stock"]
                stock = [_probe(window, i, p["candidates"]) for i, p in enumerate(projected)]
                if "baseline" in row and encoded(stock) != encoded(row["baseline"]):
                    raise ValueError("same-IQ stock candidate output differs from its archive")
                measured = account(data, targets)
            outputs.append(dict(row, status=status, **measured))
        controls = {}
        for index, (name, sample, targets) in enumerate(synthetic(edge)):
            data = measure(sample, *args, index=index)
            controls[name] = dict(iq_sha256=_digest(sample.tobytes()), **account(data, targets))
    return dict(edge=edge, measured=outputs, controls=controls, lock_sha256=_digest(encoded(lock)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "lower", "upper"))
    parser.add_argument("--work", type=local_output, default=center_union_build.WORK)
    args = parser.parse_args()
    target = REPORT / "source-lock.json.gz"
    if args.stage == "freeze":
        if target.exists():
            raise ValueError("complete saved-IQ roster already frozen")
        write(target, gzip.compress(encoded(freeze(args.work)), mtime=0))
        return
    lock = load(target)
    for name, digest in lock["inputs"].items():
        whole_iq.checked(ROOT / name, digest)
    for role, path in lock["paths"].items():
        whole_iq.checked(Path(path), lock["sha256"][role])
    data = replay(args.stage, lock)
    write(REPORT / f"{args.stage}.json.gz", gzip.compress(encoded(data), mtime=0))


if __name__ == "__main__":
    main()
