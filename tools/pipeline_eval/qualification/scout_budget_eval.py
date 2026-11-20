"""Measure held saved-IQ scout neighborhoods against authenticated archived factors."""

import argparse
import gzip
import json
import os
import subprocess
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, write
from ..variants import iq_stream, scout_budget
from . import ordinary_front_build, ordinary_front_eval, scout_budget_build, wide_regional_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import (
    BULK,
    PRODUCERS,
    _bind_producer,
    _from_native,
    _load_case,
    _probe,
    _sha,
    compare_probes,
)
from .pilot_kernel_eval import _digest, _windows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/scout-budget"
SCHEDULE = tuple((segment, (10, 14, 19, 25)) for segment in (1, 5, 11))
DEV = ((3, (0, 2)),)
MODES = ("control", "scout16")
RATE = 10_000_000
PROBE = Path(__file__).with_name("scout_budget_probe.c")
FRAME = 13333


def sources():
    return {
        p.name: _sha(p)
        for p in (
            Path(__file__),
            Path(scout_budget.__file__),
            scout_budget.HEADER,
            Path(scout_budget_build.__file__),
            Path(ordinary_front_eval.__file__),
            Path(wide_regional_eval.__file__),
            Path(iq_stream.__file__),
            PROBE,
            REPORT / "PROTOCOL.md",
        )
    }


def release(work):
    output = json.loads((work / "host-release.json").read_bytes())
    for mode in MODES:
        if _sha(Path(output["paths"][mode])) != output["library_sha256"][mode]:
            raise ValueError("Released scout digest differs from built data")
    if output["library_sha256"]["control"] != scout_budget_build.PIN:
        raise ValueError("Off arm differs from the canonical four-center wide release")
    return output


def make_probe(work):
    target = work / "probe"
    if target.is_file():
        return target
    base = work / "scout16-source" / "kernel"
    receipt = json.loads((work / "scout16" / "build-receipt.json").read_bytes())
    fftwf = ordinary_front_build.HOST_FFTW / "lib" / "libfftw3f.a"
    if _sha(fftwf) != receipt["fftw_float_archive_sha256"]:
        raise ValueError("Probe frequency transforms differ from release archive")
    subprocess.run(
        [
            receipt["compiler"],
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(base),
            "-I",
            str(base / "private"),
            str(PROBE),
            str(work / "scout16" / "libleo-adaptive-detector.a"),
            str(fftwf),
            "-lm",
            "-o",
            str(target),
        ],
        env={**os.environ, "TMPDIR": str(work / "compiler-temp")},
        check=True,
    )
    return target


def centers_for(runner, samples, folder, template):
    iq = folder / "visit.ci16"
    samples.tofile(iq)
    value = subprocess.check_output([str(runner), str(template), str(iq)], text=True, timeout=10)
    result = [list(map(int, line.split())) for line in value.splitlines()]
    if len(result) != 2 or any(len(row) > 16 or len(set(row)) != len(row) for row in result):
        raise ValueError("Probe returned invalid RX geometry or duplicate centers")
    for row in result:
        if any(x < 0 or x >= FRAME for x in row):
            raise ValueError("Scout center escaped the ordinary epoch range")
        if any(min(abs(a - b), FRAME - abs(a - b)) < 5 for i, a in enumerate(row) for b in row[:i]):
            raise ValueError("Native circular peak exclusion differs")
    return result


def native_call(stack, library, edge, rate=RATE, frac=True):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    pair = wide_regional_eval.templates(rate, edge)
    contexts = {
        m: stack.enter_context(
            NativeShortWindow(
                library["paths"][m],
                *pair,
                sample_rate_hz=rate,
                fractional_epoch=frac,
            )
        )
        for m in MODES
    }

    def call(samples, mode):
        start = perf_counter()
        result = contexts[mode].analyze(samples, include_timings=True)
        return result, dict(wall_s=perf_counter() - start)

    return call, pair


def timed(samples, call, index, repeats):
    with patch.object(ordinary_front_eval, "MODES", MODES):
        measured = ordinary_front_eval.benchmark(samples, call, index, repeats)
    for d in measured["payloads"].values():
        wide_regional_eval.validate(d, 800_000 if d["sample_rate_hz"] == RATE else 400_000)
    if not measured["stable"]:
        raise ValueError("Repeated native candidate output is not stable")
    return measured


def archive_audit(case, timings, window_by_visit):
    path = BULK / case["native"]["path"]
    if _sha(path) != case["native"]["sha256"]:
        raise ValueError("Capture-era factor authority changed")
    archive = json.loads(path.read_bytes())
    if (
        archive["source"]["session_id"] != case["session_id"]
        or archive["provenance"]["run_id"] != case["run_id"]
    ):
        raise ValueError("Capture-era archive binding differs")
    probes = {
        (p["visit_index"], p["receiver_id"]): p
        for p in archive["source"]["probes"]
        if p["visit_index"] in window_by_visit
    }
    excluded = {
        r["visit"]: r
        for r in archive["provenance"]["excluded_windows"]
        if r["visit"] in window_by_visit
    }
    out = []
    for row in timings:
        window = window_by_visit[row["visit"]]
        if row["status"] != "processed":
            authority = excluded[row["visit"]]
            if authority["iq_sha256"] != window.iq_sha256 or authority["reason"] != row["reason"]:
                raise ValueError("The fresh capture policy changed an archive exclusion")
            continue
        if row["visit"] in excluded:
            raise ValueError("The fresh detector saw an excluded original visit")
        for j, rx in enumerate(window.receiver_ids):
            old = probes[row["visit"], rx]
            positives = [c for c in old["candidates"] if c["passed_fractional_margin_gate"]]
            fits, cover = {}, {}
            for mode, n in (("control", 4), ("scout16", 16)):
                current = row["payloads"][mode]["rows"][j]
                support = row["centers"][j][:n]
                allowed = {p for c in support for p in range(max(0, c - 1), min(FRAME, c + 2))}
                cover[mode] = [
                    dict(
                        rank=c["candidate_rank"],
                        integer_epoch=c["integer_epoch_sample"],
                        exact=c["integer_epoch_sample"] in allowed,
                        nearest_circular_samples=min(
                            (
                                min(
                                    abs(p - c["integer_epoch_sample"]),
                                    FRAME - abs(p - c["integer_epoch_sample"]),
                                )
                                for p in support
                            ),
                            default=None,
                        ),
                    )
                    for c in positives
                ]
                raw = (_from_native(i, c) for i, c in enumerate(current["candidates"]))
                fits[mode] = compare_probes(old, _probe(window, rx, raw), RATE)
            out.append(
                dict(
                    visit=row["visit"],
                    receiver=rx,
                    archive_positive_count=len(positives),
                    archive_candidates=positives,
                    scout_coverage=cover,
                    native_fit=fits,
                )
            )
    return dict(native_archive_sha256=case["native"]["sha256"], receivers=out)


def held(ident, work, bank, dev=False):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(ident), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[ident], policy)
    folder = work / f"{ident}-{'dev' if dev else 'held'}"
    folder.mkdir(exist_ok=False)
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
        windows = [w for seg, seq in (DEV if dev else SCHEDULE) for w in _windows(case, seg, seq)]
    observed = []
    with ExitStack() as stack:
        call, pair = native_call(stack, bank, windows[0].target["edge"])
        template = folder / "exact.c128"
        pair[0].tofile(template)
        for i, w in enumerate(windows):
            result = analyze_window(
                w,
                w.receiver_ids,
                None,
                policy,
                detector=lambda _w, ids: tuple(
                    FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in ids
                ),
            )
            values = {}
            if result.status == "processed":
                values = timed(w.samples, call, i, 1 if dev else 5)
                values["centers"] = centers_for(make_probe(work), w.samples, folder, template)
            observed.append(
                dict(
                    values,
                    visit=result.visit,
                    status=result.status,
                    reason=result.reason,
                    sequence=w.sequence,
                    iq_sha256=w.iq_sha256,
                    iq_bytes=w.samples.nbytes,
                )
            )
    write(folder / "fresh-before-archive.json.gz", gzip.compress(encoded(observed), mtime=0))
    evidence = (
        {}
        if dev
        else archive_audit(case, observed, {w.acquisition["global_visit"]: w for w in windows})
    )
    return dict(
        id=ident,
        producer=producer,
        release=bank,
        rows=observed,
        archive=evidence,
        fresh_receipt_sha256=_sha(folder / "fresh-before-archive.json.gz"),
    )


def smoke(work, bank):
    results = {}
    for edge, sign in (("lower", 1), ("upper", -1)):
        examples = {
            "signed-high": ((735, sign * 688_125, 640),),
            "weak": ((997, sign * 193_450, 128),),
            "very-weak": ((1091, sign * 193_450, 8),),
            "two": ((735, sign * 688_125, 640), (3027, -sign * 387_625, 232)),
        }
        input_ = wide_regional_eval.synthetic(RATE, edge)
        folder = work / f"smoke-{edge}"
        folder.mkdir(exist_ok=False)
        with ExitStack() as stack:
            call, pair = native_call(stack, bank, edge)
            template = folder / "exact.c128"
            pair[0].tofile(template)
            for k, (label, plants) in enumerate(examples.items()):
                w = _test_signal(input_, plants, 82801 + k)
                result = timed(w.samples, call, k, 1)
                centers = centers_for(make_probe(work), w.samples, folder, template)
                if label == "signed-high" and not all(
                    any(abs(c[1] - 735) <= 2 and abs(c[2] - plants[0][1]) < 1000 for c in rx)
                    for rx in result["positives"]["scout16"]
                ):
                    raise ValueError("Scout16 failed signed high-CFO canary")
                results[f"{edge}-{label}"] = dict(
                    result, centers=centers, iq_sha256=w.iq_sha256, planted=plants
                )
            for label, samples in (
                ("empty", np.zeros_like(input_.samples)),
                ("noise", _test_signal(input_, (), 82805).samples),
            ):
                result = timed(samples, call, 0, 1)
                centers = centers_for(make_probe(work), samples, folder, template)
                results[f"{edge}-{label}"] = dict(
                    result, centers=centers, iq_sha256=_digest(samples.tobytes())
                )
                if label == "empty" and (any(centers) or not result["exact"]):
                    raise ValueError("The empty scout must not emit a synthetic center")
    return dict(release=bank, results=results, same_release_probe_sha256=_sha(make_probe(work)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_budget_build.ROOT)
    p.add_argument("--case", choices=PRODUCERS)
    p.add_argument("--dev", action="store_true")
    args = p.parse_args()
    bank = release(args.work)
    frozen = sources()
    if frozen != json.loads((REPORT / "source-lock.json").read_bytes()):
        raise ValueError("Frozen scout source differs")
    if args.case:
        result = held(args.case, args.work, bank, args.dev)
        name = f"{args.case}-{'dev' if args.dev else 'held'}.json.gz"
    else:
        result = smoke(args.work, bank)
        name = "smoke.json.gz"
    if frozen != sources():
        raise ValueError("Scout source changed during held replay")
    write(REPORT / name, gzip.compress(encoded(result), mtime=0))
