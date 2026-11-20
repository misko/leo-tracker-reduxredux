"""Measure thinned full-support nomination in the deployed capture-era detector."""

import argparse
import gzip
import json
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import thinned_capture
from ..variants.iq_stream import load_windows
from . import capture_detector_lineage as lineage
from .capture_detector_replay import scan_capture_window
from .full_v5_check import BULK, _from_native, _load_case, _probe, _sha, compare_probes

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/thinned-capture"
CASES = lineage.CASES
WIDE = Path("/srv/bulk/leo-dev/20261119-wide-regional/wide/libleo-adaptive-detector.so")
WIDE_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
ROSTER = dict(
    zip(
        CASES,
        (
            ((0, 1), (0, 6), (13, 6)),
            ((0, 1), (6, 6), (13, 1)),
            ((0, 1), (13, 1)),
            ((0, 1), (0, 6), (6, 1)),
        ),
        strict=True,
    )
)
MODES = ("capture", "thinned", "wide")
CONTROLS = (CASES[0], CASES[3])


def _digest(payload):
    return "sha256:" + sha256(payload).hexdigest()


def source_lock():
    if _sha(WIDE) != WIDE_SHA:
        raise ValueError("the paired wide library differs from its measured survey build")
    prior = json.loads((lineage.REPORT / "source-lock.json").read_bytes())["files"]
    sources = (
        Path(__file__),
        Path(thinned_capture.__file__),
        Path(lineage.__file__),
        REPORT / "PROTOCOL.md",
        lineage.REPORT / "source-lock.json",
    )
    pinned = {}
    for ident, slots in ROSTER.items():
        path = lineage.REPORT / f"{ident}.json.gz"
        if _sha(path) != prior[path.name]:
            raise ValueError("archive-stratification source differs from its seal")
        d = json.loads(gzip.decompress(path.read_bytes()))
        mapping = {(r["segment"], r["sequence"]): r for r in d["rows"]}
        pinned[ident] = [
            dict(
                segment=s,
                sequence=q,
                visit=mapping[s, q]["visit"],
                iq_sha256=mapping[s, q]["iq_sha256"],
                status=mapping[s, q]["status"],
            )
            for s, q in slots
        ]
    return dict(sources={str(p): _sha(p) for p in sources}, wide_sha256=WIDE_SHA, roster=pinned)


def ms(start):
    return (process_time_ns() - start) / 1e6


def shape(peaks):
    return [[int(epoch), float(cfo)] for _, epoch, cfo in peaks]


def capture(window, policy, thinned):
    from leo.analysis.starlink import acquisition as acq
    from leo.scanner import fast_scan_detector as detector

    clocks, calls, grids = defaultdict(float), [], {}
    source_grid, source_peaks = acq._folded_anchor_score_grid, acq._retain_score_map_peaks
    acquire = detector.acquire_symbolwise
    screen = None
    if find_spec("leo.analysis.starlink.coarse_screen") is not None:
        from leo.analysis.starlink import coarse_screen

        screen = coarse_screen.acquire

    def timed(function, key):
        def call(*args, **kwargs):
            start = process_time_ns()
            result = function(*args, **kwargs)
            clocks[key] += ms(start)
            return result

        return call

    def worker(samples, rate, calibration, *, edge, config):
        residuals = acq._bounded_grid(
            config.residual_cfo_min_hz, config.residual_cfo_max_hz, config.coarse_cfo_step_hz
        )
        packet = dict(
            rx=int(calibration.receiver_id),
            anchors=len(config.anchor_symbols),
            center_hz=calibration.center_hz,
            cfo_lanes=len(residuals),
            peaks=[],
        )
        key = (packet["rx"], packet["anchors"])

        def grid(*args):
            start = process_time_ns()
            if thinned:
                values, detail = thinned_capture.propose(
                    acq,
                    args,
                    residuals,
                    config.candidate_epoch_separation_samples,
                    config.candidate_cfo_separation_hz,
                    source_peaks,
                )
                packet.update(detail)
            else:
                values = source_grid(*args)
                packet["original_cells"] = len(residuals) * args[-1]
            clocks["coarse_grid"] += ms(start)
            grids[key] = values
            return values

        def retain(*args):
            start = process_time_ns()
            result = source_peaks(*args)
            clocks["final_peak_select"] += ms(start)
            packet["peaks"] = shape(result)
            return result

        def screened(module, args, residual, count, separate_epochs, separate_cfo):
            if thinned:
                values = grid(*args)
                return values, retain(
                    residual, values, count, separate_epochs, separate_cfo, args[-1]
                )
            start = process_time_ns()
            values, peaks = screen(module, args, residual, count, separate_epochs, separate_cfo)
            clocks["coarse_and_peaks_screened"] += ms(start)
            packet.update(original_cells=len(residual) * args[-1], peaks=shape(peaks))
            return values, peaks

        start = process_time_ns()
        with ExitStack() as stack:
            if screen is None:
                stack.enter_context(
                    patch.multiple(
                        acq, _folded_anchor_score_grid=grid, _retain_score_map_peaks=retain
                    )
                )
            else:
                stack.enter_context(patch.object(coarse_screen, "acquire", screened))
            result = acquire(samples, rate, calibration, edge=edge, config=config)
        clocks["acquisition_inclusive"] += ms(start)
        calls.append(packet)
        return result

    wall, cpu = perf_counter_ns(), process_time_ns()
    with (
        patch.multiple(
            detector,
            acquire_symbolwise=worker,
            conditioned_glrt64_scores=timed(detector.conditioned_glrt64_scores, "integer_glrt"),
            refine_glrt64_epochs=timed(detector.refine_glrt64_epochs, "fractional_glrt"),
        ),
        patch.multiple(
            acq,
            _normalized_frame_scores=timed(acq._normalized_frame_scores, "fine"),
            _conditioned_frame_scores=timed(acq._conditioned_frame_scores, "conditioned"),
        ),
    ):
        result, probes = scan_capture_window(window, window.receiver_ids, policy)
    return dict(
        status=result.status,
        probes=probes,
        acquisitions=calls,
        stage_cpu_ms=dict(clocks),
        wall_ms=(perf_counter_ns() - wall) / 1e6,
        cpu_ms=ms(cpu),
    ), grids


def wide_call(context, window):
    wall, cpu = perf_counter_ns(), process_time_ns()
    native = context.analyze(window.samples, include_timings=True)
    probes = [
        _probe(
            window,
            row["receiver_id"],
            (_from_native(i, c) for i, c in enumerate(row["candidates"])),
        )
        for row in native["rows"]
    ]
    return dict(
        status="processed",
        probes=probes,
        acquisitions=[],
        detector_cpu_ms=native["detector_cpu_ms"],
        stage_cpu_ms=[r["timings_ms"] for r in native["rows"]],
        wall_ms=(perf_counter_ns() - wall) / 1e6,
        cpu_ms=ms(cpu),
    )


def measure(window, policy, context, reps, index):
    paired = []
    for rep in range(reps):
        results, matrices = {}, {}
        offset = (index + rep) % len(MODES)
        for mode in MODES[offset:] + MODES[:offset]:
            if mode == "wide":
                results[mode] = wide_call(context, window)
            else:
                results[mode], matrices[mode] = capture(window, policy, mode == "thinned")
        comparable = 0
        for key in matrices["capture"].keys() & matrices["thinned"].keys():
            original = np.asarray(matrices["capture"][key])
            sparse = np.asarray(matrices["thinned"][key])
            accepted = np.isfinite(sparse)
            if not np.array_equal(original[accepted], sparse[accepted]):
                raise ValueError("native full-support rescoring changed an evaluated coarse cell")
            comparable += np.count_nonzero(accepted)
        paired.append(dict(modes=results, bit_exact_rescored_cells=int(comparable)))
    for mode in MODES:
        if any(
            encoded(r["modes"][mode]["probes"]) != encoded(paired[0]["modes"][mode]["probes"])
            for r in paired[1:]
        ):
            raise ValueError("matched candidate payload changed between repetitions")
    reference = paired[0]["modes"]["capture"]["probes"]
    return dict(
        pairs=paired,
        positives={
            m: [
                compare_probes(original, trial, window.sample_rate_hz)
                for original, trial in zip(reference, paired[0]["modes"][m]["probes"], strict=True)
            ]
            for m in ("thinned", "wide")
        },
    )


def controls(window):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    shape = window.samples.shape
    rng = np.random.default_rng(502031)
    noise = rng.normal(0, 500, shape)
    exact = qin_edge_pilot_frame(window.sample_rate_hz, window.target["edge"])
    out = {"empty": np.zeros(shape, dtype="<i2"), "noise": np.rint(noise).astype("<i2")}
    for name, epoch, cfo, amplitude in (("weak", 735, 48_000, 128), ("high", 731, 720_000, 600)):
        raw = np.zeros(shape[0], dtype=np.complex128)
        for i in range(15):
            start = epoch + round(i * window.sample_rate_hz / 750)
            size = min(raw.size - start, len(exact))
            raw[start : start + size] = exact[:size]
        raw *= amplitude * np.exp(2j * np.pi * cfo * np.arange(raw.size) / window.sample_rate_hz)
        iq = np.stack((raw.real, raw.imag), axis=-1)[:, None, :]
        out[name] = np.clip(np.rint(iq + noise), -32768, 32767).astype("<i2")
    return {k: replace(window, samples=v, iq_sha256=_digest(v.tobytes())) for k, v in out.items()}


def replay(ident, lock):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    case = _load_case(ident)
    meta, policy, provenance = lineage.source_lineage(case)
    reference = json.loads(gzip.decompress((lineage.REPORT / f"{ident}.json.gz").read_bytes()))
    refs = {r["visit"]: r for r in reference["rows"]}
    rate, edge = 10_000_000, meta["edge"]
    templates = [
        np.asarray(qin_edge_pilot_frame(rate, edge, symbol_roll=r), dtype="<c16")
        for r in (0, CONTROL_SYMBOL_ROLL)
    ]
    rows, synthetic = [], {}
    with NativeShortWindow(
        str(WIDE), *templates, sample_rate_hz=rate, fractional_epoch=True
    ) as context:
        for index, key in enumerate(lock["roster"][ident]):
            segment, sequence = key["segment"], key["sequence"]
            locator = case["recording"]["segments"][segment]
            (window,) = load_windows(
                dict(
                    recording_path=str(BULK / locator["path"]),
                    recording_sha256="sha256:" + locator["sha256"],
                ),
                (sequence,),
            )
            if (
                window.iq_sha256 != key["iq_sha256"]
                or window.acquisition["global_visit"] != key["visit"]
            ):
                raise ValueError("matched authentic visit IQ changed")
            status = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _, ids: tuple(
                    FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids
                ),
            ).status
            if status != key["status"]:
                raise ValueError("matched capture validity changed")
            result = {}
            if status == "processed":
                if not synthetic and ident in CONTROLS:
                    panel = controls(window)
                    measure(panel["empty"], policy, context, 1, 0)
                    synthetic = {
                        k: dict(iq_sha256=x.iq_sha256, **measure(x, policy, context, 1, i))
                        for i, (k, x) in enumerate(panel.items())
                    }
                result = measure(window, policy, context, 2, index)
                baseline = result["pairs"][0]["modes"]["capture"]["probes"]
                if encoded(baseline) != encoded(refs[key["visit"]]["capture"]):
                    raise ValueError("capture reference differs from its authenticated probe bytes")
            rows.append(dict(key, **result))
    return dict(
        id=ident,
        provenance=provenance,
        rows=rows,
        controls=synthetic,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        locked_sha256=_digest(encoded(lock)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", *CASES))
    args = parser.parse_args()
    lock = source_lock()
    target = REPORT / "source-lock.json"
    if args.stage == "freeze":
        if target.exists():
            raise ValueError("the thinned detector plan already has a source lock")
        save_json(target, lock)
    else:
        if json.loads(target.read_bytes()) != lock:
            raise ValueError("thinned detector source or fixed roster differs from preflight")
        data = replay(args.stage, lock)
        write(local_output(REPORT / f"{args.stage}.json.gz"), gzip.compress(encoded(data), mtime=0))
