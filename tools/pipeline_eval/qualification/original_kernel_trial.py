"""Benchmark the prepared original coarse grid in the authenticated capture detector."""

import argparse
import gzip
import json
import os
import subprocess
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import capture_fft, iq_stream, original_kernel
from ..variants.selective_capture import visit_pairs
from . import capture_exact_trial as previous
from . import capture_release
from . import capture_runtime as auth
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import BULK, _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-support/original-kernel"
WORK = auth.WORK.with_name("original-kernel-v1")
MODES = ("installed", "combined", "prepared")
CASES = {"DS26-0237": (0, 72), "DS29-0082": (1, 13), "DS29-0519": (0, 157), "DS29-0174": (1, None)}
HISTORIC = "b9c3dab46d4d34106d9c5b8e20fbaa80a761fa7b5f27a3097891ddccff4c1e2f"
PYTHON = Path("/opt/leo-fast-auto/20261010-r1/venv/bin/python")
MAX_PREFIX = 96 * 1_600_000


def choose(probes):
    rows = [(v, p) for v, p in visit_pairs(probes) if 20 <= v <= 95]
    first, both = rows[0]
    frequency = both[0]["actual_rf_hz"]
    second = next(v for v, p in rows[1:] if frequency == p[0]["actual_rf_hz"])
    return (first, second)


def locate(case, wanted):
    base = 0
    for pos, doc in enumerate(case["recording"]["segments"]):
        path = BULK / doc["path"]
        raw = iq_stream._read_prefix(path, 65537)
        if len(raw) > 65536 or sha256(raw).hexdigest() != doc["sha256"]:
            raise ValueError("recorded capture manifest changed from its lock")
        count = json.loads(raw)["window_count"]
        if base <= wanted < base + count:
            return pos, wanted - base, path, doc["sha256"]
        base += count
    raise ValueError("scheduled valid visit does not appear in capture inventory")


def decode(case, visit):
    segment, sequence, path, digest = locate(case, visit)
    policy = dict(recording_path=str(path), recording_sha256="sha256:" + digest)
    with patch.multiple(iq_stream, MAX_CHUNK_PREFIX=MAX_PREFIX, MAX_DECODE_BYTES=MAX_PREFIX):
        (window,) = iq_stream.load_windows(policy, (sequence,))
    if window.acquisition["global_visit"] != visit or window.samples.shape != (200_000, 2, 2):
        raise ValueError("scheduled input was not a full authentic dual-receiver visit")
    return segment, digest, window


def freeze(work):
    work.mkdir()
    saved = auth.read(auth.checked(previous.REPORT / "qualification-lock.json", HISTORIC))["files"]
    prior = auth.read(auth.checked(previous.REPORT / "source-lock.json", saved["source-lock.json"]))
    for name, h in prior["sources"].items():
        auth.checked(Path(name), h)
    binary, command = original_kernel.build(work)
    libs = {n: prior["libraries"][n] for n in ("batched32", "cfo", "fused")}
    libs["prepared"] = dict(path=str(binary), sha256=_sha(binary))
    roster = {}
    for name, (cpu, hard) in CASES.items():
        case = _load_case(name)
        receipt = capture_release.read_capture(case)
        installed = capture_release.producer(case, receipt)
        file, digest = previous.lineage.locked_native(case, "capture")
        doc = auth.read(auth.checked(file, digest.removeprefix("sha256:")))
        probes = doc["source"]["probes"]
        visits = choose(probes)
        by_visit = dict(visit_pairs(probes))
        material = []
        for v in sorted(visits if hard is None else (*visits, hard)):
            segment, manifest, w = decode(case, v)
            if [p["valid_start_counter"] for p in by_visit[v]] != [
                w.acquisition["sample_start"]
            ] * 2:
                raise ValueError("native factors do not share the original hardware sample clock")
            material.append(
                dict(
                    visit=v,
                    kind="new" if v in visits else "stress",
                    iq_sha256=w.iq_sha256,
                    sequence=w.sequence,
                    segment=segment,
                    manifest_sha256=manifest,
                    target=w.target,
                    counter=w.acquisition["sample_start"],
                    probes=by_visit[v],
                )
            )
        sources = [
            installed.root / "leo/scanner/fast_scan_analysis.py",
            installed.root / "leo/scanner/fast_scan_detector.py",
        ]
        starlink = installed.root / "leo/analysis/starlink"
        for glob in (
            "acquisition.py",
            "templates.py",
            "fast_scan_scores.py",
            "_native_acquisition*.so",
            "*screen*.py",
            "_screen_native/*.so",
            "_sparse_native/*.so",
        ):
            sources.extend(starlink.glob(glob))
        roster[name] = dict(
            cpu=cpu,
            edge=receipt["edge"],
            rows=material,
            root=str(installed.root),
            input_manifest=installed.input_manifest_sha256,
            archive_sha256=digest,
            sources={str(f): _sha(f) for f in sources},
        )
    paths = (
        Path(__file__),
        Path(original_kernel.__file__),
        original_kernel.HEADER,
        work / "folded_bank.c",
        work / "capture_fft.c",
        REPORT / "PROTOCOL.md",
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3"),
    )
    save_json(
        work / "source-lock.json",
        dict(
            cases=roster,
            previous_sha256=HISTORIC,
            libs=libs,
            build=command,
            python_sha256=_sha(PYTHON),
            sources={str(p): _sha(p) for p in paths},
        ),
    )


def rank_gap(scores, frequencies, count, radius, separation):
    left = np.pad(scores[:, :-1], ((0, 0), (1, 0)), constant_values=-np.inf)
    right = np.pad(scores[:, 1:], ((0, 0), (0, 1)), constant_values=-np.inf)
    peaks = (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    work = np.where(peaks, scores, -np.inf)
    gaps = []
    for _ in range(count):
        winner = work.max()
        if winner <= 0:
            break
        lanes, epochs = np.nonzero(work == winner)
        idx = np.lexsort((lanes, epochs, np.abs(frequencies[lanes])))[0]
        lane, epoch = lanes[idx], epochs[idx]
        work[lane, epoch] = -np.inf
        second = work.max()
        gaps.append(float(winner - second) if np.isfinite(second) else None)
        nearby = np.flatnonzero(np.abs(frequencies - frequencies[lane]) <= separation)
        circular = (epoch + np.arange(1 - radius, radius)) % scores.shape[1]
        work[np.ix_(nearby, circular)] = -np.inf
    return gaps


def inspect_grid(window, policy, combined, prepared):
    from leo.analysis.starlink import acquisition

    original = acquisition._folded_anchor_score_grid
    retain = acquisition._retain_score_map_peaks
    screen = previous.starts.screen_module()
    rows = []
    pending = []

    def measurements(args):
        stored = tuple(original(*args))
        return np.asarray(stored), *(
            np.asarray(o.score_grid(acquisition, original, *args)) for o in (combined, prepared)
        )

    def record(grids, residuals, count, separation_epoch, separation_hz, epochs):
        stored, before, after = grids
        difference = float(np.max(np.abs(before - after)))
        drift = float(np.max(np.abs(stored - after)))
        gaps = rank_gap(stored, np.array(residuals), count, separation_epoch, separation_hz)
        ranks = [
            [
                (e, f)
                for _, e, f in retain(
                    residuals, tuple(a), count, separation_epoch, separation_hz, epochs
                )
            ]
            for a in grids
        ]
        rows.append(
            dict(
                cells=stored.size,
                delta_from_combined=difference,
                delta_from_direct=drift,
                minimum_direct_gap=min((x for x in gaps if x is not None), default=None),
                close_steps=sum(x is not None and x <= 2 * drift for x in gaps),
                retained_keys_exact=ranks[0] == ranks[1] == ranks[2],
            )
        )

    if screen is None:

        def dense(*args):
            grids = measurements(args)
            pending.append(grids)
            return tuple(grids[0])

        def audited(residuals, scores, *parameters):
            record(pending.pop(), residuals, *parameters)
            return retain(residuals, scores, *parameters)

        with patch.multiple(
            acquisition, _folded_anchor_score_grid=dense, _retain_score_map_peaks=audited
        ):
            previous.starts.coarse_prefix(window, policy)
    else:
        stock = screen.acquire

        def screened(module, args, residuals, *opts, **kwargs):
            record(measurements(args), residuals, *opts, args[-1])
            return stock(module, args, residuals, *opts, **kwargs)

        with patch.object(screen, "acquire", screened):
            previous.starts.coarse_prefix(window, policy)
    if len(rows) != 2:
        raise ValueError("primary grid trace missed a physical receiver")
    return rows


def worker(work, name):
    sealed = work / "source-lock.json"
    lock = auth.read(sealed)
    for file, digest in lock["sources"].items():
        auth.checked(Path(file), digest)
    auth.checked(PYTHON, lock["python_sha256"])
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong pinned replay CPU")
    case = _load_case(name)
    _, policy, producer = previous.lineage.source_lineage(case)
    if (producer["capture"]["root"], producer["capture"]["input_manifest_sha256"]) != (
        cfg["root"],
        cfg["input_manifest"],
    ):
        raise ValueError("wrong capture-era analyzer imported")
    for file, digest in cfg["sources"].items():
        auth.checked(Path(file), digest)
    libraries = {n: auth.checked(Path(p["path"]), p["sha256"]) for n, p in lock["libs"].items()}
    grids = {
        "installed": None,
        "combined": capture_fft.FullGrid(libraries["batched32"]),
        "prepared": original_kernel.PersistentGrid(libraries["prepared"]),
    }
    working = []
    for row in cfg["rows"]:
        segment, manifest, w = decode(case, row["visit"])
        if [segment, manifest, w.iq_sha256, w.sequence, w.acquisition["sample_start"]] != [
            row[k] for k in ("segment", "manifest_sha256", "iq_sha256", "sequence", "counter")
        ]:
            raise ValueError("raw decode does not agree with prospective exact capture lock")
        working.append((str(row["visit"]), row["kind"], w, row["probes"]))
    first = next(w for _, tag, w, _ in working if tag == "new")
    if name in ("DS26-0237", "DS29-0082"):
        zeros = np.zeros_like(first.samples)
        quiet = replace(
            first, samples=zeros, iq_sha256="sha256:" + sha256(zeros.tobytes()).hexdigest()
        )
        sgn = 1 if cfg["edge"] == "lower" else -1
        working.extend(
            (
                ("flat", "control", quiet, None),
                (
                    "signed",
                    "control",
                    _test_signal(quiet, ((735, sgn * 720_000, 128),), 78201),
                    None,
                ),
            )
        )
    rows = []
    grid_checks = []
    try:
        for r in range(2):
            for j, (label, tag, w, ref) in enumerate(working):
                p = (j + r) % len(MODES)
                for mode in MODES[p:] + MODES[:p]:
                    grid = grids[mode]
                    if grid is not None:
                        grid.calls.clear()
                    if mode == "installed":
                        value = previous.stages.detector(w, policy, None)
                        if ref is not None and value["probes"] != ref:
                            raise ValueError(
                                "capture original does not reproduce the sealed archive factors"
                            )
                    else:
                        with previous.refiners(libraries):
                            value = previous.stages.detector(w, policy, grid)
                    rows.append(
                        dict(
                            label=label,
                            kind=tag,
                            repeat=r,
                            mode=mode,
                            iq_sha256=w.iq_sha256,
                            data=value,
                        )
                    )
                print(name, label, r, flush=True)
        grid_checks = inspect_grid(first, policy, grids["combined"], grids["prepared"])
    finally:
        grids["prepared"].clear_cache()
        write(
            work / f"{name}.json.gz",
            gzip.compress(
                encoded(
                    dict(
                        rows=rows,
                        grid=grid_checks,
                        cpu=cfg["cpu"],
                        producer=producer,
                        lock_sha256=_sha(sealed),
                    )
                ),
                mtime=0,
            ),
        )


def run(work, names):
    lock = auth.read(work / "source-lock.json")
    for name in names:
        c = lock["cases"][name]
        env = os.environ | {"PYTHONPATH": f"{c['root']}:{ROOT}"}
        for lib in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[lib + "_NUM_THREADS"] = "1"
        cmd = [
            "taskset",
            "-c",
            str(c["cpu"]),
            str(PYTHON),
            "-u",
            "-m",
            __spec__.name,
            "worker",
            str(work),
            name,
        ]
        subprocess.run(cmd, cwd=ROOT, env=env, timeout=110, check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "worker", "run"))
    p.add_argument("work", type=local_output, nargs="?", default=WORK)
    p.add_argument("names", choices=tuple(CASES), nargs="*")
    args = p.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.work, args.names[0])
    else:
        run(args.work, args.names)
