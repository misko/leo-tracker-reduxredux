"""Check the saved-IQ boundary of the authentic capture-era fast-scan detector."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import (
    anchor_grid,
    conditioned_cfo_bank,
    fractional_adjoint,
    iq_stream,
    pilot_kernel,
    refine_bank,
    spectral_grid,
)
from .full_v5_check import (
    BULK,
    NATIVE_LIBRARY,
    PRODUCERS,
    REPO,
    _bind_producer,
    _from_native,
    _from_production,
    _load_case,
    _probe,
    _sha,
)
from .pilot_kernel_eval import _windows

REPORT = REPO / "reports/2026_11_19_receiver_screening/detector-origins/raw-boundary"
ROSTER = {6: (11, 17), 12: (11, 17)}
PINS = {"DS26-0036": 12, "DS29-0082": 13}


def fingerprint(samples):
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(samples)).hexdigest()


def raw_authority(window, receivers):
    return dict(
        sequence=window.sequence,
        iq_sha256=window.iq_sha256,
        raw_sha256=fingerprint(window.samples),
        dtype=window.samples.dtype.str,
        shape=list(window.samples.shape),
        rate_hz=window.sample_rate_hz,
        receivers=list(receivers),
        column_sha256=[fingerprint(window.samples[:, j]) for j in range(len(receivers))],
        acquisition=window.acquisition,
        target=window.target,
    )


def installed_reader(locator, segment):
    from leo.storage.fast_scan import FastSegmentSource

    manifest = (BULK / locator["path"]).resolve()
    if manifest.name != "manifest.json" or not manifest.is_relative_to(
        BULK / "leo/fast-scan-recordings"
    ):
        raise ValueError("installed reader needs the declared immutable IQ manifest")
    chosen = set(ROSTER[segment])
    source = FastSegmentSource(
        dict(path=str(manifest.parent), manifest_digest="sha256:" + locator["sha256"]),
        start_sequence=min(chosen),
        stop_sequence=max(chosen) + 1,
    )
    return dict(
        rows=[
            raw_authority(w, source.receiver_ids) for w in source.windows() if w.sequence in chosen
        ],
        radio=source.radio,
        capture_configuration=source.reader.manifest.configuration,
        sample_format=source.reader.manifest.sample_format,
        sample_layout=source.reader.manifest.sample_layout,
        manifest_sha256=source.manifest_digest,
    )


def compact_and_installed(ident, case, segment):
    # Use the configured read-only acquisition account and consume its emitted receipts only.
    value = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "leo",
            "--",
            "env",
            f"PYTHONPATH={PRODUCERS[ident].root}:{REPO}",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            sys.executable,
            "-B",
            "-m",
            __spec__.name,
            "reader",
            json.dumps(case["recording"]["segments"][segment]),
            str(segment),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if value.returncode:
        raise ValueError(f"installed archive reader failed: {value.stderr.strip()}")
    installed = json.loads(value.stdout)
    # The fixed roster can extend through 18 × 1.6 MB of decoded prefix in one chunk.
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 32 * iq_stream.MIB):
        compact = _windows(case, segment, ROSTER[segment])
    comparison = [raw_authority(w, w.receiver_ids) for w in compact]
    if comparison != installed["rows"] or any(
        x["raw_sha256"] != x["iq_sha256"] for x in comparison
    ):
        raise ValueError("compact and capture-era readers disagree on authenticated saved IQ")
    return compact, installed


def metadata(row):
    return {k: v for k, v in row.items() if k != "candidates"}


def index_probes(document):
    keyed = {(r["visit_index"], r["receiver_id"]): r for r in document["source"]["probes"]}
    if len(keyed) != len(document["source"]["probes"]):
        raise ValueError("this acquisition has more than one scheduled probe per receiver")
    return keyed


def compare_clocks(capture, ordinary):
    old, new = map(index_probes, (capture, ordinary))
    shared = old.keys() & new.keys()
    fields = ("clock_anchor", "delivery_clocks", "last_sample_counter")
    return dict(
        exact={k: capture[k] == ordinary[k] for k in fields},
        shared_receivers=len(shared),
        missing=len(old.keys() - new.keys()),
        extras=len(new.keys() - old.keys()),
        changed_metadata=sum(metadata(old[k]) != metadata(new[k]) for k in shared),
    )


def load_bound(path, digest):
    if _sha(path) != digest:
        raise ValueError("frozen native factor file changed")
    return json.loads(path.read_bytes())


def ordinary_factor(ident):
    base = REPORT.parent.parent / "end-to-end"
    lock = json.loads((base / "prediction-lock.json").read_bytes())
    proof_file = base / "stage-receipts.json"
    proof = load_bound(proof_file, lock["files"][proof_file.name])[ident]
    digest = proof["raw_replay"]["native_sha256"]
    if (
        not proof["same_factors_as_prior_whole_iq"]
        or digest != proof["prior_complete_iq"]["native_sha256"]
    ):
        raise ValueError("ordinary factors lack the paired complete recording authority")
    return load_bound(
        Path("/tmp/leo-secant-end-to-end-20261119") / ident / "native.json", digest
    ), digest


def witness(analysis, detector, window, policy, mode):
    original = analysis.analyze_glrt64_dwell
    initial = detector._evaluate_probe
    calls, dwell = [], {}

    def evidence(
        probe, configuration, calibration, *, edge, acquisition_config, receiver_id, probe_index
    ):
        calls.append(
            dict(
                receiver_id=receiver_id,
                probe_index=probe_index,
                count=len(probe),
                dtype=probe.dtype.str,
                contiguous=bool(probe.flags.c_contiguous),
                probe_sha256=fingerprint(probe),
                center_hz=calibration.center_hz,
                anchors=list(acquisition_config.anchor_symbols),
                range_hz=[
                    acquisition_config.residual_cfo_min_hz,
                    acquisition_config.residual_cfo_max_hz,
                ],
            )
        )
        return initial(
            probe,
            configuration,
            calibration,
            edge=edge,
            acquisition_config=acquisition_config,
            receiver_id=receiver_id,
            probe_index=probe_index,
        )

    def analysis_inputs(samples, configuration, *, edge, search_geometry):
        raw = window.samples
        original_decode = (
            samples.shape == raw.shape[:2]
            and np.array_equal(samples.real, raw[:, :, 0])
            and np.array_equal(samples.imag, raw[:, :, 1])
        )
        dwell.update(
            ci16_exact_unscaled=bool(original_decode),
            dtype=samples.dtype.str,
            shape=list(samples.shape),
            receiver_ids=list(configuration.receiver_ids),
            start_index=0,
            probe_samples=configuration.probe_samples,
            stride_samples=configuration.probe_stride_samples,
            n_probes=configuration.scheduled_probe_count,
            center_hz=[cal.center_hz for cal in search_geometry.receiver_calibrations],
            cfo_range_hz=[search_geometry.residual_cfo_min_hz, search_geometry.residual_cfo_max_hz],
            fallback_anchors=list(search_geometry.fallback_anchor_symbols),
        )
        if mode == "no-paired-fallback":
            search_geometry = replace(search_geometry, fallback_anchor_symbols=())
        elif mode == "swap-receivers":
            samples = np.ascontiguousarray(samples[:, ::-1])
        elif mode == "half-complex-gain":
            samples = samples * np.float32(0.5)
        elif mode == "drop-first-sample":
            shifted = np.zeros_like(samples)
            shifted[:-1] = samples[1:]
            samples = shifted
        dwell["probe_input_sha256"] = [
            fingerprint(np.ascontiguousarray(samples[:, k], dtype=np.complex128))
            for k in range(samples.shape[1])
        ]
        return original(samples, configuration, edge=edge, search_geometry=search_geometry)

    start, cpu = perf_counter(), process_time()
    with (
        patch.object(analysis, "analyze_glrt64_dwell", analysis_inputs),
        patch.object(detector, "_evaluate_probe", evidence),
    ):
        result = analysis.analyze_window(window, window.receiver_ids, None, policy)
    return result, dict(
        wall_s=perf_counter() - start, cpu_s=process_time() - cpu, dwell=dwell, calls=calls
    )


@contextmanager
def faster(path):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_detector

    compilers = dict(
        tiled=pilot_kernel.compile_filter,
        spectral=spectral_grid.compile_filter,
        fused=refine_bank.compile_bank,
        cfo=conditioned_cfo_bank.compile_bank,
        adjoint=fractional_adjoint.compile_bank,
    )
    outputs = {name: path / (name + ".so") for name in compilers}
    for name, build in compilers.items():
        build(outputs[name])
    coarse = spectral_grid.SpectralGrid(
        outputs["spectral"], anchor_grid.native_grid(outputs["tiled"])
    )
    fused = refine_bank.RefinementBank(outputs["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("compiled fitter has an incompatible FFT")
    conditioner = conditioned_cfo_bank.ConditionedBank(outputs["cfo"], acquisition)
    adjoint = fractional_adjoint.Adjoint(outputs["adjoint"], fused)
    guarded = conditioner.guarded_acquisition(fast_scan_detector.acquire_symbolwise)
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)
    bindings = (
        (acquisition, "_folded_anchor_score_grid", coarse.score_grid),
        (acquisition, "_retain_score_map_peaks", coarse.retain_peaks),
        (acquisition, "_conditioned_frame_scores", conditioner.score),
        (fast_scan_detector, "acquire_symbolwise", guarded),
        (fast_scan_detector, "conditioned_glrt64_scores", fused.integer),
        (fast_scan_scores, "conditioned_glrt64_scores", fused.integer),
        (fast_scan_scores, "conditioned_glrt64_score", adjoint.score),
        (fast_scan_scores, "fractional_take", sampler),
    )

    @contextmanager
    def configured():
        for reset in (coarse.receipts.clear, fused.reset, conditioner.reset, adjoint.reset):
            reset()
        with ExitStack() as restore:
            for module, name, func in bindings:
                restore.enter_context(patch.object(module, name, func))
            yield

    yield configured


def as_probes(window, result):
    return [
        _probe(window, rx.receiver_id, map(_from_production, rx.candidates))
        for rx in result.receivers
    ]


def positives(probes):
    return [
        {
            **metadata(r),
            "candidates": [c for c in r["candidates"] if c["passed_fractional_margin_gate"]],
        }
        for r in probes
    ]


def sources():
    modules = (
        anchor_grid,
        conditioned_cfo_bank,
        fractional_adjoint,
        iq_stream,
        pilot_kernel,
        refine_bank,
        spectral_grid,
    )
    paths = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        NATIVE_LIBRARY,
        *(Path(m.__file__) for m in modules),
        *(m.SOURCE for m in modules if hasattr(m, "SOURCE")),
    )
    for producer in PRODUCERS.values():
        paths += tuple(
            producer.root / "leo" / suffix
            for suffix in (
                "scanner/fast_scan_analysis.py",
                "scanner/fast_scan_detector.py",
                "storage/short_window.py",
                "storage/fast_scan.py",
                "analysis/starlink/native_short_window.py",
            )
        )
    return {str(p): _sha(p) for p in paths}


def run(ident, workspace):
    from leo.analysis.starlink import native_short_window, templates
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_analysis as analysis
    from leo.scanner import fast_scan_detector as detector

    if os.sched_getaffinity(0) != {PINS[ident]} or os.nice(0) < 10:
        raise ValueError("capture raw boundary must use its declared CPU and priority")
    frozen = json.loads((workspace.parent / "source-lock.json").read_bytes())
    if frozen["files"] != sources():
        raise ValueError("saved-IQ study source changed")
    workspace.mkdir(exist_ok=False)
    case, policy = _load_case(ident), FastScanPolicyV2()
    root = _bind_producer(case, PRODUCERS[ident], policy)
    archive = load_bound(BULK / case["native"]["path"], case["native"]["sha256"])
    ordinary, authority = ordinary_factor(ident)
    old, archived_c = map(index_probes, (archive, ordinary))
    edge, rate = ("upper" if ident.startswith("DS29") else "lower"), policy.sample_rate_hz
    exact = np.asarray(templates.qin_edge_pilot_frame(rate, edge), dtype="<c16")
    control = np.asarray(
        templates.qin_edge_pilot_frame(rate, edge, symbol_roll=templates.CONTROL_SYMBOL_ROLL),
        dtype="<c16",
    )
    rows, installed = [], {}
    first_processed = True
    with (
        native_short_window.NativeShortWindow(
            str(NATIVE_LIBRARY),
            exact,
            control,
            sample_rate_hz=rate,
            receiver_count=2,
            fractional_epoch=True,
        ) as ordinary_c,
        faster(workspace) as accelerated,
    ):
        for segment in ROSTER:
            windows, installed[segment] = compact_and_installed(ident, case, segment)
            for window in windows:
                visit = window.acquisition["global_visit"]
                output, audit = witness(analysis, detector, window, policy, "production")
                row = dict(
                    segment=segment,
                    visit=visit,
                    sequence=window.sequence,
                    iq_sha256=window.iq_sha256,
                    status=output.status,
                    policy=output.model_dump(mode="json", exclude={"receivers"}),
                    archive_probe_metadata=[
                        metadata(old[visit, rx]) for rx in window.receiver_ids if (visit, rx) in old
                    ],
                    production=audit,
                )
                if output.status == "processed":
                    original = as_probes(window, output)
                    archived = [old[visit, rx] for rx in window.receiver_ids]
                    archived_ordinary = [archived_c[visit, rx] for rx in window.receiver_ids]
                    row.update(probes=original, exact_archive=original == archived)
                    start, cpu = perf_counter(), process_time()
                    current = ordinary_c.analyze(window.samples)
                    c_clock = dict(wall_s=perf_counter() - start, cpu_s=process_time() - cpu)
                    ordinary_rows = [
                        _probe(
                            window,
                            p["receiver_id"],
                            (_from_native(i, c) for i, c in enumerate(p["candidates"])),
                        )
                        for p in current["rows"]
                    ]
                    row["ordinary"] = dict(
                        c_clock,
                        probes=ordinary_rows,
                        exact_ordinary_archive=ordinary_rows == archived_ordinary,
                    )
                    with accelerated():
                        quicker, costs = witness(analysis, detector, window, policy, "production")
                    fast = as_probes(window, quicker)
                    row["accelerated"] = dict(
                        costs, probes=fast, positive_exact=positives(fast) == positives(original)
                    )
                    changes = ["no-paired-fallback"]
                    if first_processed:
                        changes.extend(("swap-receivers", "half-complex-gain", "drop-first-sample"))
                    row["controls"] = {}
                    for mode in changes:
                        alternate, timing = witness(analysis, detector, window, policy, mode)
                        row["controls"][mode] = dict(timing, probes=as_probes(window, alternate))
                    first_processed = False
                rows.append(row)
                print(ident, visit, output.status, row.get("exact_archive"), flush=True)
    report = dict(
        case=ident,
        producer=root,
        ordinary_factor_sha256=authority,
        capture_factor_sha256=case["native"]["sha256"],
        metadata=compare_clocks(archive, ordinary),
        readers=installed,
        rows=rows,
        accelerator_binaries={p.name: _sha(p) for p in workspace.glob("*.so")},
    )
    write(workspace / "result.json.gz", gzip.compress(encoded(report), mtime=0))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("reader", "run", "seal"))
    p.add_argument("key")
    p.add_argument("value", nargs="?")
    args = p.parse_args()
    if args.mode == "reader":
        print(encoded(installed_reader(json.loads(args.key), int(args.value))).decode())
    elif args.mode == "seal":
        target = local_output(Path(args.key)) / "source-lock.json"
        if target.exists():
            raise FileExistsError(target)
        save_json(target, dict(files=sources(), roster=ROSTER, pins=PINS))
    else:
        run(args.key, local_output(Path(args.value)))
