"""Trace the installed capture-era acquisition and replay its exact coarse timing prefix."""

import argparse
import gzip
import importlib.util
import json
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream
from . import capture_detector_lineage, capture_release, hinted_glrt_trial, oracle_start
from .capture_detector_replay import scan_capture_window
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _from_native, _load_case, _probe, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/capture-starts"
ORACLE = oracle_start.REPORT
CASES = oracle_start.CASES
CONTROL_CASES = ("DS26-0237", "DS29-0082")
POLICY_HZ = 10_000_000


def screen_module():
    name = "leo.analysis.starlink.coarse_screen"
    return importlib.import_module(name) if importlib.util.find_spec(name) is not None else None


def freeze(work):
    lock_path = ORACLE / "result-lock.json"
    parents = json.loads(lock_path.read_bytes())
    if any(_sha(ORACLE / f) != h for f, h in parents["files"].items()):
        raise ValueError("oracle-start evidence differs from its immutable seal")
    source = json.loads((ORACLE / "input-lock.json").read_bytes())["cases"]
    cases = {}
    for ident in CASES:
        case = _load_case(ident)
        receipt = capture_release.read_capture(case)
        producer = capture_release.producer(case, receipt)
        starlink = producer.root / "leo/analysis/starlink"
        closure = {
            str(p): _sha(p)
            for p in (
                starlink / "acquisition.py",
                starlink / "templates.py",
                *starlink.glob("fast_scan_*.py"),
                *starlink.glob("*screen*.py"),
                *starlink.glob("_native_acquisition*.so"),
                *starlink.glob("_screen_native/*.so"),
                *starlink.glob("_sparse_native/*.so"),
                producer.root / "leo/scanner/fast_scan_analysis.py",
                producer.root / "leo/scanner/fast_scan_detector.py",
            )
        }
        chosen = source[ident]["selected"]
        if len(chosen) != 6 or any(r["archive_probe"]["edge"] != receipt["edge"] for r in chosen):
            raise ValueError("the four original case rosters must keep their authenticated edges")
        cases[ident] = dict(
            edge=receipt["edge"],
            producer=str(producer.root),
            sources=closure,
            input_manifest_sha256=producer.input_manifest_sha256,
            visits=[row["visit"] for row in chosen],
            archived_native_sha256=case["native"]["sha256"],
        )
    files = (
        Path(__file__),
        Path(iq_stream.__file__),
        Path(capture_release.__file__),
        Path(capture_detector_lineage.__file__),
        Path(scan_capture_window.__code__.co_filename),
        Path(hinted_glrt_trial.__file__),
        Path(oracle_start.__file__),
        Path(_test_signal.__code__.co_filename),
        ORACLE / "input-lock.json",
        lock_path,
        oracle_start.ABI,
        REPORT / "PROTOCOL.md",
    )
    save_json(work / "input-lock.json", dict(cases=cases, sources={str(p): _sha(p) for p in files}))


def plan(work):
    receipt = json.loads((work / "input-lock.json").read_bytes())
    if any(_sha(Path(path)) != digest for path, digest in receipt["sources"].items()):
        raise ValueError("capture-start plan differs from the frozen code or archive roster")
    return receipt["cases"], json.loads((ORACLE / "input-lock.json").read_bytes())["cases"]


def peak_rows(peaks):
    return [dict(score=float(s), epoch=int(e), residual_cfo_hz=float(f)) for s, e, f in peaks]


def trace_capture(window, policy):
    from leo.analysis.starlink import acquisition as acq
    from leo.scanner import fast_scan_detector as detector

    screen = screen_module()
    original = detector._evaluate_probe
    acquired = detector.acquire_symbolwise
    attempts = []
    per_lane = defaultdict(int)

    def evaluate(
        probe, configuration, calibration, *, edge, acquisition_config, receiver_id, probe_index
    ):
        try_i = per_lane[receiver_id]
        per_lane[receiver_id] += 1
        packet = dict(
            receiver=receiver_id,
            attempt="primary" if not try_i else "fallback",
            probe_index=probe_index,
            anchors=list(acquisition_config.anchor_symbols),
            centers=[],
            stage_cpu_ns={},
            stage_calls={},
        )
        clocks, calls = defaultdict(int), defaultdict(int)

        def observe(fn, key, projection=None):
            def run(*args, **kwargs):
                start = process_time_ns()
                result = fn(*args, **kwargs)
                clocks[key] += process_time_ns() - start
                calls[key] += 1
                if projection is not None:
                    projection(args, kwargs, result)
                return result

            return run

        def retain(_args, _kwargs, response):
            packet["centers"] = peak_rows(response)

        def screened(_args, _kwargs, response):
            packet["centers"] = peak_rows(response[1])

        def acquisition(_args, _kwargs, response):
            packet["acquired"] = [asdict(c) for c in response.candidates]

        def search(key):
            def entries(args, _kwargs, result):
                packet.setdefault(key, []).append(
                    dict(
                        epoch=int(args[3]),
                        cfo_grid_hz=list(args[4]),
                        scores=list(result),
                    )
                )

            return entries

        with ExitStack() as hooks:
            if screen is None:
                hooks.enter_context(
                    patch.object(
                        acq,
                        "_folded_anchor_score_grid",
                        observe(acq._folded_anchor_score_grid, "coarse_grid"),
                    )
                )
                hooks.enter_context(
                    patch.object(
                        acq,
                        "_retain_score_map_peaks",
                        observe(acq._retain_score_map_peaks, "coarse_selection", retain),
                    )
                )
            else:
                hooks.enter_context(
                    patch.object(
                        screen,
                        "acquire",
                        observe(screen.acquire, "coarse_screened_and_selection", screened),
                    )
                )
            for module, name, key, projection in (
                (detector, "acquire_symbolwise", "acquisition_inclusive", acquisition),
                (acq, "_normalized_frame_scores", "fine", search("fine_search")),
                (acq, "_conditioned_frame_scores", "conditioned", search("conditioned_search")),
                (detector, "conditioned_glrt64_scores", "integer_glrt", None),
                (detector, "refine_glrt64_epochs", "fractional_glrt", None),
            ):
                impl = acquired if name == "acquire_symbolwise" else getattr(module, name)
                hooks.enter_context(patch.object(module, name, observe(impl, key, projection)))
            result = original(
                probe,
                configuration,
                calibration,
                edge=edge,
                acquisition_config=acquisition_config,
                receiver_id=receiver_id,
                probe_index=probe_index,
            )
        packet.update(
            stage_cpu_ns=dict(clocks),
            stage_calls=dict(calls),
            final_candidates=[asdict(c) for c in result.candidates],
            passes=bool(result.has_fractional_detection(configuration.glrt64_margin_gate)),
        )
        attempts.append(packet)
        return result

    cpu, wall = process_time_ns(), perf_counter_ns()
    with patch.object(detector, "_evaluate_probe", evaluate):
        result, probes = scan_capture_window(window, window.receiver_ids, policy)
    return dict(
        attempts=attempts,
        probes=probes,
        status=result.status,
        cpu_ns=process_time_ns() - cpu,
        wall_ns=perf_counter_ns() - wall,
    )


def coarse_prefix(window, policy):
    """Use only the production primary score and its adjacent-cell epoch correction."""
    from leo.analysis.starlink import acquisition as acq
    from leo.scanner import fast_scan_detector as detector

    screen = screen_module()
    choices = []

    def evaluate(probe, config, calibration, *, edge, acquisition_config, receiver_id, probe_index):
        del probe_index
        cpu, wall = process_time_ns(), perf_counter_ns()
        cfg = acquisition_config
        rate = config.sample_rate_hz
        residuals = acq._bounded_grid(
            cfg.residual_cfo_min_hz, cfg.residual_cfo_max_hz, cfg.coarse_cfo_step_hz
        )
        absolute = tuple(calibration.absolute_cfo_hz(f) for f in residuals)
        template = np.asarray(acq.qin_edge_pilot_frame(rate, edge), np.complex128)
        epochs = round(rate / acq.FRAME_RATE_HZ)
        args = probe, template, rate, absolute, cfg.anchor_symbols, epochs
        ranking = (
            cfg.retained_candidate_count,
            cfg.candidate_epoch_separation_samples,
            cfg.candidate_cfo_separation_hz,
        )
        if screen is None:
            grid = acq._folded_anchor_score_grid(*args)
            peaks = acq._retain_score_map_peaks(residuals, grid, *ranking, epochs)
        else:
            grid, peaks = screen.acquire(acq, args, residuals, *ranking)
        if peaks and peaks[0][0] > 0:
            _, epoch, residual = peaks[0]
            hint = int(acq._refine_epoch(grid[residuals.index(residual)], epoch, epochs))
        else:
            hint = None
        choices.append(
            dict(
                receiver=receiver_id,
                hint=hint,
                centers=peak_rows(peaks),
                anchors=len(cfg.anchor_symbols),
                cfo_rows=len(residuals),
                epochs=epochs,
                cpu_ns=process_time_ns() - cpu,
                wall_ns=perf_counter_ns() - wall,
            )
        )
        return detector._ProbeEvaluation((), ())

    cpu, wall = process_time_ns(), perf_counter_ns()
    with patch.object(detector, "_evaluate_probe", evaluate):
        result, _ = scan_capture_window(window, window.receiver_ids, policy)
    return dict(
        choices=choices,
        status=result.status,
        cpu_ns=process_time_ns() - cpu,
        wall_ns=perf_counter_ns() - wall,
    )


def replay_case(work, ident):
    cases, original = plan(work)
    control = cases[ident]
    case = _load_case(ident)
    _, policy, producer = capture_detector_lineage.source_lineage(case)
    if (
        producer["capture"]["root"] != control["producer"]
        or producer["capture"]["input_manifest_sha256"] != control["input_manifest_sha256"]
        or any(_sha(Path(f)) != h for f, h in control["sources"].items())
    ):
        raise ValueError("capture worker did not import the sealed installed firmware release")
    scratch = work / ident
    scratch.mkdir()
    products = []
    for row in original[ident]["selected"]:
        window = hinted_glrt_trial.load_selected(case, row)
        path = scratch / f"visit-{row['visit']}.ci16"
        write(path, window.samples.tobytes())
        capture = trace_capture(window, policy)
        prefix = coarse_prefix(window, policy)
        for choice in prefix["choices"]:
            actual = next(a for a in capture["attempts"] if a["receiver"] == choice["receiver"])
            if actual["centers"] != choice["centers"]:
                raise ValueError(
                    "standalone prefix differs from the installed first coarse ranking"
                )
        products.append(
            dict(
                visit=row["visit"],
                capture=capture,
                prefix=prefix,
                metadata=dict(
                    sequence=window.sequence,
                    receiver_ids=window.receiver_ids,
                    sample_rate_hz=window.sample_rate_hz,
                    acquisition=window.acquisition,
                    target_id=window.target_id,
                    target=window.target,
                    iq_sha256=window.iq_sha256,
                ),
            )
        )
        print(
            ident,
            row["visit"],
            [(r["receiver"], r["attempt"]) for r in capture["attempts"]],
            flush=True,
        )
    controls = {}
    if ident in CONTROL_CASES:
        geometry = iq_stream.IQWindow(
            0,
            np.zeros((200000, 2, 2), dtype="<i2"),
            (0, 1),
            POLICY_HZ,
            window.acquisition,
            window.target_id,
            window.target,
            "",
        )
        signed_hz = 720_000 if control["edge"] == "lower" else -720_000
        for name, plants in (("signed", ((735, signed_hz, 640),)), ("noise", ())):
            plant = _test_signal(geometry, plants, 78201)
            controls[name] = dict(
                prefix=coarse_prefix(plant, policy),
                capture=trace_capture(plant, policy),
                plants=plants,
            )
    output = dict(capture=products, controls=controls, producer=producer)
    write(work / f"{ident}-capture.json.gz", gzip.compress(encoded(output), mtime=0))


def wide(work, ident):
    cases, original = plan(work)
    capture_path = work / f"{ident}-capture.json.gz"
    observed = json.loads(gzip.decompress(capture_path.read_bytes()))
    by_visit = {row["visit"]: row for row in observed["capture"]}
    libs = json.loads(oracle_start.ABI.read_bytes())
    for key, path in libs["paths"].items():
        if _sha(Path(path)) != libs["library_sha256"][key]:
            raise ValueError("wide libraries differ from the paired oracle study")
    outcomes = []
    with ExitStack() as stack:
        stock, hinted = hinted_glrt_trial.bound(stack, libs["paths"], cases[ident]["edge"])
        for i, row in enumerate(original[ident]["selected"]):
            visit, rx = row["visit"], row["receiver"]
            data = by_visit[visit]
            raw = (work / ident / f"visit-{visit}.ci16").read_bytes()
            if "sha256:" + sha256(raw).hexdigest() != row["iq_sha256"]:
                raise ValueError(
                    "shared scratch waveform differs from the originally authenticated CI16"
                )
            window = iq_stream.IQWindow(
                samples=np.frombuffer(raw, dtype="<i2").reshape(200000, 2, 2), **data["metadata"]
            )
            choices = {r["receiver"]: r["hint"] for r in data["prefix"]["choices"]}
            hints = tuple(choices[j] if j == rx else None for j in (0, 1))
            result = hinted_glrt_trial.measure(
                window.samples, stock, hinted, dict(causal=hints, sham=row["sham"]), i, reps=2
            )
            probes = {
                m: [
                    _probe(
                        window, r, (_from_native(q, c) for q, c in enumerate(lane["candidates"]))
                    )
                    for r, lane in zip(window.receiver_ids, p["rows"], strict=True)
                ]
                for m, p in result["payloads"].items()
            }
            if encoded(probes["stock"]) != encoded(row["baseline"]):
                raise ValueError("wide stock probe parity failed")
            outcomes.append(
                dict(visit=visit, receiver=rx, hints=hints, result=result, probes=probes)
            )
    write(
        work / f"{ident}-wide.json.gz",
        gzip.compress(encoded(dict(outputs=outcomes, capture_sha256=_sha(capture_path))), mtime=0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "capture", "wide"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    directory = local_output(args.work)
    directory.mkdir(parents=True, exist_ok=True)
    if args.mode == "freeze":
        if (directory / "input-lock.json").exists():
            raise FileExistsError("stage inputs already sealed")
        freeze(directory)
    elif args.case is None:
        parser.error("a capture or wide worker must name one sealed case")
    elif args.mode == "capture":
        replay_case(directory, args.case)
    else:
        wide(directory, args.case)
