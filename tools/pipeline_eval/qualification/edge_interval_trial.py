"""Use blinded compact packets for a signed subscan position interval experiment."""

import argparse
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import edge_interval
from . import edge_evidence_trial as old
from . import edge_holdouts as prior
from .fresh_scenes import _destination, _read, _sha

REPORT = prior.REPORT.parents[1] / "next/edge-interval"
CPUS = (9, 10)
METHOD = "v5_secant_subscan_interval"
WORKER = Path(__file__).with_name("edge_interval_worker.py")
SITES = (((37.0, -92.0), (0.72, 1.25)), ((-44.0, -70.0), (1.2, 1.85)))
CASE_S = 105
TOTAL_S = 555
MEASURED = "DS26-0036-22km-east"


def dispatch(tasks, root, *, started):
    legacy = old.legacy
    kernel = root / "projector.so"
    legacy.compact.orbit_projector.compile_kernel(kernel)
    invoke = legacy.compact.invoke

    def sandbox(args, data, timeout):
        if args[-1] == "interval":
            args[-1], args[-3] = "gate", "/trial/interval.py"
            binds = [(WORKER, "/trial/interval.py"), (old.WORKER, "/trial/held-face.py")]
            for module in (edge_interval, old.edge_evidence, prior.edge):
                path = Path(module.__file__)
                binds.append((path, f"/worker/tools/pipeline_eval/variants/{path.name}"))
            for path, target in binds:
                args[-5:-5] = ("--ro-bind", str(path), target)
        return invoke(args, data, timeout)

    def lane(cpu, jobs):
        rows = []
        for job, mode in jobs:
            left = int(TOTAL_S - (perf_counter() - started))
            if left < 10:
                result = legacy.compact.portable_v5.unavailable("batch window expired")
                rows.append(
                    dict(job[0], method=METHOD, mode=mode, result=result, wall_s=None, trace=[])
                )
                continue
            record = legacy.run_one(job, kernel, cpu, mode, min(CASE_S, left))
            rows.append(dict(record, mode=mode))
        return rows

    with (
        patch.object(legacy, "METHODS", legacy.METHODS | {"interval": METHOD}),
        patch.object(legacy.compact, "invoke", sandbox),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        workers = [pool.submit(lane, cpu, tasks[i::2]) for i, cpu in enumerate(CPUS)]
        return [row for future in workers for row in future.result()]


def diagnosis(root, old_root):
    public = _read(old.REPORT / "public-captures.json")
    by_id = {
        r["id"]: r
        for r in _read(old.REPORT / "scores.json")
        if r["method"] == old.METHOD and r["arm"] == "c0"
    }
    southern_pairs = [
        row
        for rows, _ in prior.jobs(old_root, public)
        for row in rows
        if by_id[row[0]["id"]]["true_margin_km"] != 0
        and by_id[row[0]["id"]]["role"].startswith("near-")
        and abs(by_id[row[0]["id"]]["true_margin_km"]) > 1
    ]
    save_json(
        root / "diagnostics.json",
        dispatch([(j, "interval") for j in southern_pairs], root, started=perf_counter()),
    )


def prior_context():
    old_sites, used = old.prior_context()
    known = _read(old.REPORT / "released-labels.json")
    public = _read(old.REPORT / "public-captures.json")
    for ident, labels in known.items():
        old_sites.add(tuple(labels["location"]))
        used.update((labels["trajectory"]["sha256"], public[ident]["source"]["sha256"]))
    return old_sites, used


def run(root):
    started = perf_counter()
    pinned = (
        Path(__file__),
        WORKER,
        Path(edge_interval.__file__),
        old.WORKER,
        Path(old.edge_evidence.__file__),
        Path(prior.edge.__file__),
        old.legacy.WORKER,
        Path(old.legacy.rule.__file__),
        Path(old.legacy.compact.v5_secant_fit.__file__),
        Path(prior.__file__),
        REPORT / "PROTOCOL.md",
    )
    save_json(
        REPORT / "source-lock.json",
        old.legacy.compact.portable.source_lock() | {str(path): _sha(path) for path in pinned},
    )
    with patch.multiple(prior, SITES=SITES, prior_context=prior_context):
        captures = list(prior.draw(root, [secrets.token_bytes(32) for _ in SITES]))
    panels = list(prior.jobs(root, captures))
    compact = old.legacy.compact
    native, offered, stamps, objects, _, _ = compact.portable.authentic_roof()
    known_measured = next(
        r for r in _read(compact.REPORT / "requests.json") if r["id"] == compact.ROOF
    )
    tile = dict(
        id=MEASURED, center=_destination(offered["center"], 22.0, 1.5707963267948966), width_km=25.0
    )
    packet = compact.bound_job(
        {
            k: v
            for k, v in known_measured.items()
            if k in ("capture_id", "native_sha256", "catalog_sha256")
        }
        | {"id": MEASURED},
        native,
        tile,
        stamps,
        objects,
    )
    # Retain an independent wrong-tile stock replay, ahead of the larger interval matrix.
    tasks = [(panels[0][0][-1], "control")]
    tasks.extend((job, "interval") for r in range(4) for rows, _ in panels for job in (rows[r],))
    tasks.append((packet, "interval"))
    roster = [dict(job[0], mode=mode) for job, mode in tasks]
    locks = {
        str(f.relative_to(root)): _sha(f)
        for d in ("public", "private")
        for f in sorted((root / d).iterdir())
    }
    save_json(REPORT / "inputs.json", locks)
    save_json(REPORT / "history.json", {c: p[1] for c, p in zip(captures, panels, strict=True)})
    save_json(REPORT / "requests.json", roster)
    rows = dispatch(tasks, root, started=started)
    if any(_sha(root / name) != value for name, value in locks.items()):
        raise ValueError("prospective input changed after seal")
    save_json(REPORT / "predictions.json", rows)
    evidence = (
        "predictions.json",
        "requests.json",
        "inputs.json",
        "history.json",
        "source-lock.json",
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            files={name: _sha(REPORT / name) for name in evidence},
            wall_s=perf_counter() - started,
        ),
    )
    for file, folder in (("released-labels.json", "private"), ("public-captures.json", "public")):
        save_json(REPORT / file, {c: _read(root / folder / f"{c}.json") for c in captures})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--diagnose", type=Path)
    args = cli.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        cli.error("pin the requested two CPU lanes")
    if args.diagnose:
        diagnosis(local_output(args.root), args.diagnose)
    else:
        run(local_output(args.root))
