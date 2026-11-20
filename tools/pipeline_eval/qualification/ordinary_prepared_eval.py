"""Build and profile the bounded ordinary GLRT prepared-input reuse experiment."""

import argparse
import ctypes as ct
import gzip
import json
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median, quantiles
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream, ordinary_prepared
from . import ordinary_front_build as build_stock
from . import ordinary_front_eval as ordinary
from . import ordinary_glrt_eval as archive
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import BULK, NATIVE_LIBRARY, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows

REPORT = ROOT / "reports/2026_11_19_receiver_screening/integration/glrt-hot-stage"
CASES = ("DS26-0036", "DS29-0082")
MODES = ("control", "ordinary_prepared")
STAGES = ("allocation", "preparation", "proposals", "search", "cleanup")
BOUNDARY = "Authenticated saved dual-RX CI16 visit through ordinary native GLRT candidates"


def search_parts(row):
    """Decompose mode-3 search; acquisition includes the fine FFT."""
    parts = {
        "coarse": row["coarse"],
        "fine_fft": row["fine_fft"],
        "acquisition_other": row["acquisition"] - row["fine_fft"],
        "conditioned": row["conditioned"],
        "integer_glrt": row["glrt"],
        "fractional_epoch": row["fractional_epoch"],
    }
    return dict(parts, unassigned_search=row["total_cpu"] - sum(parts.values()))


class Profile(ct.Structure):
    _fields_ = [
        (f"{stage}_{clock}_ms", ct.c_double) for stage in STAGES for clock in ("cpu", "wall")
    ] + [("prepared_complex_times", ct.c_size_t)]


def build(work):
    receipt = json.loads(build_stock.CONTROL_BUILD.read_bytes())
    if any(_sha(build_stock.SOURCE / item) != sha for item, sha in receipt["sources"].items()):
        raise ValueError("The native source differs from the measured ordinary control")
    source = work / "host-source"
    shutil.copytree(build_stock.SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    native = source / "native_glrt.c"
    native.write_text(ordinary_prepared.retain_short_window_preparation(native.read_text()))
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--target",
            receipt["target"],
            "--fftw-prefix",
            str(build_stock.HOST_FFTW),
            "--output-dir",
            str(work / "host"),
            "--work-dir",
            str(work / "host-build"),
        ],
        check=True,
    )


def _profile(context):
    from leo.analysis.starlink.native_short_window import _Result

    invoke = context._library.leo_native_glrt_analyze_short_window_profiled
    invoke.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_int16),
        ct.c_size_t,
        ct.POINTER(_Result),
        ct.POINTER(Profile),
    ]
    invoke.restype = ct.c_int
    profile = Profile()

    def analyze(*args):
        return invoke(*args, ct.byref(profile))

    context._analyze = analyze
    return profile


def load_ci16(path, *, mapped):
    """Measure local saved IQ ingestion while authenticating all bytes in either path."""
    wall, cpu = perf_counter_ns(), process_time_ns()
    load = np.memmap if mapped else np.fromfile
    ci16 = load(path, dtype="<i2").reshape(200_000, 2, 2)
    digest = _digest(memoryview(ci16))
    return ci16, digest, (perf_counter_ns() - wall) / 1e6, (process_time_ns() - cpu) / 1e6


def replay(case_id, work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    previous_path = archive.REPORT / f"{case_id}-host.json.gz"
    previous = json.loads(gzip.decompress(previous_path.read_bytes()))
    # The signed archive receipts carry the original validity exclusions.
    case = _load_case(case_id)
    paths = dict(zip(MODES, (NATIVE_LIBRARY, work / "host" / NATIVE_LIBRARY.name), strict=True))
    if _sha(NATIVE_LIBRARY) != previous["executable_sha256"]["control"]:
        raise ValueError("ordinary control library differs from the archived qualification")
    inputs = work / f"{case_id}-inputs"
    inputs.mkdir(exist_ok=True)
    windows = {}
    for segment, sequences in archive.SCHEDULE:
        loc = (BULK / case["recording"]["segments"][segment]["path"]).resolve()
        if not loc.is_relative_to(iq_stream.ARCHIVE_ROOT):
            raise ValueError("held IQ must have volume-local archive files")
        with patch.object(iq_stream, "MAX_CHUNK_PREFIX", archive.CHUNK_PREFIX):
            for win in _windows(case, segment, sequences):
                windows[(segment, win.sequence)] = win
    first_row = next(row for row in previous["rows"] if row["status"] == "processed")
    first = windows[(first_row["segment"], first_row["sequence"])]
    edge = first.target["edge"]
    exact = np.asarray(qin_edge_pilot_frame(ordinary.RATE, edge), dtype="<c16")
    template = np.asarray(
        qin_edge_pilot_frame(ordinary.RATE, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    with ExitStack() as stack:
        contexts, clocks, setup = {}, {}, {}
        for mode, path in paths.items():
            started = perf_counter_ns()
            contexts[mode] = stack.enter_context(
                NativeShortWindow(
                    str(path), exact, template, sample_rate_hz=ordinary.RATE, fractional_epoch=True
                )
            )
            setup[mode] = (perf_counter_ns() - started) / 1e6
            clocks[mode] = _profile(contexts[mode])

        def call(path, mode, mapped):
            samples, iq, read_wall, read_cpu = load_ci16(path, mapped=mapped)
            start_wall, start_cpu = perf_counter_ns(), process_time_ns()
            result = contexts[mode].analyze(samples, include_timings=True)
            wall_ms = (perf_counter_ns() - start_wall) / 1e6
            cpu_ms = (process_time_ns() - start_cpu) / 1e6
            payload = encoded(ordinary._payload(result))
            return (
                iq,
                _digest(payload),
                ordinary.positive(result),
                dict(
                    wall_ms=wall_ms,
                    cpu_ms=cpu_ms,
                    read_wall_ms=read_wall,
                    read_cpu_ms=read_cpu,
                    detector_cpu_ms=result["detector_cpu_ms"],
                    profile={name: getattr(clocks[mode], name) for name, _ in Profile._fields_},
                    rows=[r["timings_ms"] for r in result["rows"]],
                ),
            )

        def measure(name, samples, reference, index, repeats=5):
            path = inputs / f"{name}.ci16"
            samples.tofile(path)
            for mode in MODES:
                call(path, mode, False)  # exclude first-context/prepared-buffer page faults
            calls = []
            for rep in range(repeats):
                order = MODES if (rep + index) % 2 == 0 else MODES[::-1]
                for mode in order:
                    for mapped in (False, True) if (rep + index) % 2 == 0 else (True, False):
                        iq, payload, positives, timing = call(path, mode, mapped)
                        if iq != reference["iq_sha256"]:
                            raise ValueError(f"saved IQ content changed for {name}")
                        calls.append(
                            dict(
                                timing,
                                mode=mode,
                                mapped=mapped,
                                repeat=rep,
                                payload_sha256=payload,
                                positives=positives,
                            )
                        )
            original_digest = reference["payload_sha256"]["control"]
            return dict(
                calls=calls,
                archive_payload_sha256=original_digest,
                archive_iq_sha256=reference["iq_sha256"],
                exact=all(c["payload_sha256"] == original_digest for c in calls),
            )

        rows = []
        for index, row in enumerate(previous["rows"]):
            identity = {k: row[k] for k in ("segment", "sequence", "visit", "status", "iq_sha256")}
            window = windows[(row["segment"], row["sequence"])]
            if window.iq_sha256 != row["iq_sha256"]:
                raise ValueError("reconstructed wave8 visit has a different IQ digest")
            if row["status"] == "processed":
                receipt = measure(f"{row['segment']}-{row['sequence']}", window.samples, row, index)
                identity.update(receipt)
            rows.append(identity)
        controls = {
            "empty": ordinary.spectral_grid_eval._synthetic(first)["empty"][0],
            "noise": ordinary._noise(first),
            "faint": _test_signal(first, ((735, 48_000, 128),), 830819),
        }
        results = {
            name: measure(name, win.samples, previous["controls"][name], j, 2)
            for j, (name, win) in enumerate(controls.items())
        }
    return dict(
        case=case_id,
        rows=rows,
        controls=results,
        context_wall_ms=setup,
        paired_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        archive_sha256=_sha(previous_path),
        libraries={m: _sha(p) for m, p in paths.items()},
    )


def timing_summary(calls):
    total = [r["wall_ms"] + r["read_wall_ms"] for r in calls]
    stages = {k: sum(r["profile"][f"{k}_cpu_ms"] for r in calls) for k in STAGES}
    search_rows = [(search_parts(r) for r in c["rows"]) for c in calls]
    search = dict.fromkeys(search_parts(calls[0]["rows"][0]), 0.0)
    for rows in search_rows:
        for parts in rows:
            for key, value in parts.items():
                search[key] += value
    detector_cpu = sum(r["detector_cpu_ms"] for r in calls)
    return dict(
        calls=len(calls),
        within_20_ms=sum(x <= 20 for x in total),
        full_wall_median_ms=median(total),
        full_wall_p90_ms=quantiles(total, n=10)[8],
        full_wall_max_ms=max(total),
        detector_wall_median_ms=median(r["wall_ms"] for r in calls),
        detector_cpu_total_ms=detector_cpu,
        read_wall_median_ms=median(r["read_wall_ms"] for r in calls),
        stages_cpu_total_ms=dict(stages, other_wrapper=detector_cpu - sum(stages.values())),
        search_cpu_total_ms=dict(
            search, other_wrapper_search=stages["search"] - sum(search.values())
        ),
    )


def package(work):
    from . import short_receiver_figures

    authority_path = short_receiver_figures.ORDINARY / "recording-receipts.json"
    authority = json.loads(authority_path.read_bytes())["recordings"]
    archive_lock = json.loads((archive.REPORT / "prediction-lock.json").read_bytes())["files"]
    docs, predictions = [], []
    for case_id in CASES:
        doc = json.loads(gzip.decompress((REPORT / f"{case_id}.json.gz").read_bytes()))
        if doc["archive_sha256"] != archive_lock[f"{case_id}-host.json.gz"]:
            raise ValueError("Archived ordinary source digest was not the sealed original")
        attempted = [r for r in doc["rows"] if r["status"] == "processed"]
        if [len(attempted), len(doc["rows"]), len(doc["controls"])] != [
            8 if case_id.startswith("DS26") else 4,
            8,
            3,
        ] or any(not r["exact"] for r in [*attempted, *doc["controls"].values()]):
            raise ValueError("Ordinary prepared qualification changed a gate or detector payload")
        doc["summary"] = {
            f"{mode}_{path}": timing_summary(
                [
                    r
                    for row in attempted
                    for r in row["calls"]
                    if r["mode"] == mode and r["mapped"] == (path == "mmap")
                ]
            )
            for mode in MODES
            for path in ("fromfile", "mmap")
        }
        docs.append(doc)
        frozen = _load_case(case_id)
        for mode, method in zip(
            MODES, ("ordinary_prepared_stock", "ordinary_prepared"), strict=True
        ):
            predictions.append(
                dict(
                    method=method,
                    id=case_id,
                    catalog_sha256=frozen["catalog"]["sha256"],
                    source_ordinary_sha256=authority[case_id]["native_sha256"],
                    native_visit_receipt_sha256=_sha(REPORT / f"{case_id}.json.gz"),
                    result=dict(
                        status="withheld",
                        boundary=BOUNDARY,
                        reason="ordinary native candidate stage only",
                        metrics=dict(
                            position_attempted=False,
                            visits=len(attempted),
                            timings=doc["summary"][f"{mode}_mmap"],
                        ),
                    ),
                )
            )
    main_calls = [r for doc in docs for row in doc["rows"] for r in row.get("calls", ())]
    summary = {
        f"{mode}_{path}": timing_summary(
            [r for r in main_calls if r["mode"] == mode and r["mapped"] == (path == "mmap")]
        )
        for mode in MODES
        for path in ("fromfile", "mmap")
    }
    source_hashes = {
        str(p.relative_to(ROOT)): _sha(p)
        for p in (
            Path(__file__).resolve(),
            Path(ordinary_prepared.__file__).resolve(),
            Path(iq_stream.__file__).resolve(),
            Path(ordinary.__file__).resolve(),
            Path(archive.__file__).resolve(),
            build_stock.CONTROL_BUILD,
            NATIVE_LIBRARY,
            REPORT / "PROTOCOL.md",
            authority_path,
        )
    }
    save_json(
        REPORT / "source-lock.json",
        dict(
            sources=source_hashes,
            archive_digests={d["case"]: d["archive_sha256"] for d in docs},
            candidate_build_receipt_sha256=_sha(work / "host/build-receipt.json"),
            candidate_library_sha256=_sha(work / "host" / NATIVE_LIBRARY.name),
        ),
    )
    save_json(
        REPORT / "qualification.json",
        dict(
            boundary=BOUNDARY,
            cases={
                d["case"]: dict(
                    timing=d["summary"],
                    context_wall_ms=d["context_wall_ms"],
                    valid_visits=sum(r["status"] == "processed" for r in d["rows"]),
                    raw_replay_runner_peak_rss_kib=d["paired_peak_rss_kib"],
                    controls={k: r["calls"][0]["positives"] for k, r in d["controls"].items()},
                )
                for d in docs
            },
            timing=summary,
            valid_visits=12,
            original_exclusions=4,
            stage_only=True,
            canonical_archive_payloads_exact=True,
        ),
    )
    write(
        REPORT / "stage-results.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in predictions), mtime=0),
    )
    names = [f"{case_id}.json.gz" for case_id in CASES] + [
        "figures.json",
        "PROTOCOL.md",
        "qualification.json",
        "source-lock.json",
        "stage-results.jsonl.gz",
    ]
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("build", "package", *CASES))
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = local_output(args.work)
    if args.task == "build":
        build(work)
        return
    if args.task == "package":
        package(work)
        return
    receipt = replay(args.task, work)
    write(REPORT / f"{args.task}.json.gz", gzip.compress(encoded(receipt), mtime=0))


if __name__ == "__main__":
    main()
