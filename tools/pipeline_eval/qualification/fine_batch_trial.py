"""Repeat the complete capture detector with exact SIMD frame batching."""

import argparse
import gzip
import os
import subprocess
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import fine_batch, fine_search, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as existing
from . import fine_search_stage as previous
from . import original_kernel_trial as original
from .capture_runtime import checked, read
from .full_v5_check import _load_case, _sha
from .prepared_hotpath_trial import sample

REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/fine-batch"
MODES = ("scalar", "batched")
REPEATS = 5


def freeze(work):
    work.mkdir()
    seal = checked(previous.REPORT / previous.MEASUREMENT_SEAL, previous.MEASUREMENT_SHA)
    authenticated = read(seal)["files"]
    panel = checked(previous.REPORT / "input-lock.json", authenticated["input-lock.json"])
    lock = read(panel)
    paths = (
        seal,
        panel,
        Path(__file__),
        Path(fine_batch.__file__),
        fine_batch.SOURCE,
        Path(fine_search.__file__),
        fine_search.SOURCE,
        REPORT / "PROTOCOL.md",
    )
    lock["sources"].update({str(path): _sha(path) for path in paths})
    library, command = fine_batch.build(work)
    lock["libs"]["batch"] = dict(path=str(library), sha256=_sha(library))
    lock.update(modes=MODES, repeats=REPEATS, batch_build=command)
    save_json(work / "input-lock.json", lock)


@contextmanager
def ports(acquisition, detector, variant, *, verify_original):
    stock = detector._evaluate_probe
    conditioned = acquisition._conditioned_frame_scores
    attempts = Counter()
    current = None
    rows = []

    def evaluate(*args, receiver_id, probe_index, **kwargs):
        nonlocal current
        key = (receiver_id, probe_index)
        current = (*key, attempts[key])
        attempts[key] += 1
        try:
            return stock(*args, receiver_id=receiver_id, probe_index=probe_index, **kwargs)
        finally:
            current = None

    def measure(port, function, other, meta):
        def call(*args, **kwargs):
            start, wall = process_time_ns(), perf_counter_ns()
            scores = function(*args, **kwargs)
            cpu_ns, wall_ns = process_time_ns() - start, perf_counter_ns() - wall
            if current is None:
                raise ValueError("CFO scoring did not bind a physical probe")
            if other is not None and scores != other(*args, **kwargs):
                raise ValueError("scalar pruned score differs from the installed full FFT")
            top = sorted(scores, reverse=True)[:2]
            _, template, rate, epoch, frequencies, *_ = args
            rows.append(
                dict(
                    port=port,
                    receiver=current[0],
                    probe=current[1],
                    attempt=current[2],
                    epoch=int(epoch),
                    first_hz=frequencies[0],
                    last_hz=frequencies[-1],
                    bins=len(scores),
                    frames=int(
                        sum(
                            epoch + start + meta(template) <= len(args[0])
                            for start in fine_search.FRAME_BASE
                        )
                    ),
                    rate=rate,
                    grid_sha256=sha256(encoded(frequencies)).hexdigest(),
                    scores_sha256=sha256(encoded(scores)).hexdigest(),
                    rank_gap=top[0] - top[1],
                    cpu_ns=cpu_ns,
                    wall_ns=wall_ns,
                    conditioned_fallback=(
                        conditioned.__self__.receipts[-1]["fallback"]
                        if port == "conditioned"
                        else None
                    ),
                )
            )
            return scores

        return call

    with (
        patch.object(detector, "_evaluate_probe", evaluate),
        patch.object(
            acquisition,
            "_normalized_frame_scores_fft",
            measure(
                "fine",
                variant.score,
                variant.original if verify_original else None,
                lambda template: fine_search.STOP,
            ),
        ),
        patch.object(
            acquisition,
            "_conditioned_frame_scores",
            measure(
                "conditioned",
                conditioned,
                None,
                len,
            ),
        ),
    ):
        yield rows


def duplicates(rows):
    frequencies, within, epochs = set(), set(), set()
    out = Counter(calls=0, repeated_exact=0, repeated_within_acquisition=0, repeated_epochs=0)
    for row in rows:
        key = row["receiver"], row["probe"], row["epoch"]
        full = (*key, row["grid_sha256"])
        same = (*full, row["attempt"])
        out.update(
            dict(
                calls=1,
                repeated_exact=int(full in frequencies),
                repeated_epochs=int(key in epochs),
                repeated_within_acquisition=int(same in within),
            )
        )
        frequencies.add(full)
        within.add(same)
        epochs.add(key)
    return dict(out)


def worker(work, name):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector

    lockfile = work / "input-lock.json"
    lock = read(lockfile)
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong pinned replay CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        checked(Path(path), digest)
    libs = {
        name: checked(Path(info["path"]), info["sha256"]) for name, info in lock["libs"].items()
    }
    case = _load_case(name)
    _, policy, producer = existing.lineage.source_lineage(case)
    capture = producer["capture"]
    if (capture["root"], capture["input_manifest_sha256"]) != (cfg["root"], cfg["input_manifest"]):
        raise ValueError("wrong capture producer")
    variants = dict(
        scalar=fine_search.FineSearch(libs["fine"], acquisition),
        batched=fine_batch.FineBatch(libs["batch"], acquisition),
    )
    if not all(item.compatible for item in variants.values()):
        raise ValueError("a fine variant failed its native arithmetic sentinel")
    grid = PersistentGrid(libs["prepared"])
    records = []
    try:
        for index, fixture in enumerate(cfg["rows"]):
            visit = fixture["visit"]
            segment, manifest, window = original.decode(case, visit)
            if (segment, manifest, window.iq_sha256) != (
                fixture["segment"],
                fixture["manifest"],
                fixture["iq_sha256"],
            ):
                raise ValueError("saved fixture differs from frozen source")
            reference, _ = sample(window, policy)
            if reference[1] != fixture["probes"]:
                raise ValueError("installed producer differs from archived factors")
            rows = []
            profiles = {}
            with (
                existing.refiners(libs),
                grid.route(acquisition, existing.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
            ):
                for rep in range(-1, REPEATS):
                    order = MODES if (rep + index) % 2 == 0 else MODES[::-1]
                    for mode in order:
                        item = variants[mode]
                        grid.calls.clear()
                        counters = (item.calls, item.frames, item.bins, item.fallbacks)
                        with item.route():
                            observed, elapsed = sample(window, policy)
                        if (
                            observed != reference
                            or not grid.calls
                            or not all(c["applied"] for c in grid.calls)
                        ):
                            raise ValueError(
                                f"{name} {visit} {mode} changed ordered payload or work"
                            )
                        increments = tuple(
                            new - old
                            for new, old in zip(
                                (item.calls, item.frames, item.bins, item.fallbacks),
                                counters,
                                strict=True,
                            )
                        )
                        if rep >= 0:
                            rows.append(
                                dict(
                                    elapsed,
                                    mode=mode,
                                    repetition=rep,
                                    first=mode == order[0],
                                    fine_calls=increments[0],
                                    fine_frames=increments[1],
                                    fine_frame_bins=increments[2],
                                    fine_fallbacks=increments[3],
                                    coarse_grids=len(grid.calls),
                                )
                            )
                for mode, item in variants.items():
                    with ports(
                        acquisition, fast_scan_detector, item, verify_original=(mode == "scalar")
                    ) as audit:
                        observed, _ = sample(window, policy)
                    if observed != reference:
                        raise ValueError(f"{name} {visit} {mode} audit changed ordered payload")
                    profiles[mode] = audit
            clocks = ("cpu_ns", "wall_ns")
            signatures = [
                [{k: v for k, v in r.items() if k not in clocks} for r in profiles[m]]
                for m in MODES
            ]
            if not signatures[0] or signatures[0] != signatures[1]:
                raise ValueError("fine or conditioned CFO audit changed a matched score tuple")
            lookups = {
                port: duplicates([r for r in signatures[0] if r["port"] == port])
                for port in ("fine", "conditioned")
            }
            fine = [r for r in signatures[0] if r["port"] == "fine"]
            expected_work = (
                len(fine),
                sum(r["frames"] for r in fine),
                sum(r["frames"] * r["bins"] for r in fine),
                0,
            )
            coverage = ("fine_calls", "fine_frames", "fine_frame_bins", "fine_fallbacks")
            if not all(tuple(call[k] for k in coverage) == expected_work for call in rows):
                raise ValueError("measured calls missed scored fine-CFO cells")
            records.append(
                dict(
                    visit=visit,
                    kind=fixture["kind"],
                    iq_sha256=window.iq_sha256,
                    public=reference[0],
                    probes=reference[1],
                    timings=rows,
                    ports=profiles,
                    repeated_keys=lookups,
                )
            )
            print(name, visit, "fine", lookups["fine"], flush=True)
    finally:
        grid.clear_cache()
    result = dict(
        case=name,
        edge=cfg["edge"],
        cpu=cfg["cpu"],
        input_lock_sha256=_sha(lockfile),
        workspace_bytes={mode: item.workspace_bytes for mode, item in variants.items()},
        rotation_cache=fine_search._rotation.cache_info()._asdict(),
        peak_rss_kib=existing.stages.resident()["hwm_kib"],
        rows=records,
    )
    write(work / f"{name}.json.gz", gzip.compress(encoded(result), mtime=0))


def run(work, names):
    lock = read(work / "input-lock.json")
    for name in names:
        cfg = lock["cases"][name]
        env = os.environ | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for backend in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[f"{backend}_NUM_THREADS"] = "1"
        command = [
            "taskset",
            "-c",
            str(cfg["cpu"]),
            str(original.PYTHON),
            "-u",
            "-m",
            __spec__.name,
            "worker",
            str(work),
            name,
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=140)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("cases", nargs="*", choices=tuple(original.CASES))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.work, args.cases[0])
    else:
        run(args.work, args.cases or tuple(original.CASES))
