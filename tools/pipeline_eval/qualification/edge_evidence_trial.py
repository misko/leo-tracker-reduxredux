"""Run a conditional local edge test through the frozen compact numerical path."""

import argparse
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import edge_evidence
from . import edge_holdouts as prior
from . import transfer_budget as legacy
from .fresh_scenes import _read, _sha

REPORT = prior.REPORT.parents[1] / "streamlined/edge-evidence"
CPUS = (14, 15, 23)
METHOD = "v5_secant_held_edge"
WORKER = Path(__file__).with_name("edge_evidence_worker.py")
SITES = (((54.0, 32.0), (0.35, 0.85)), ((-23.0, -43.0), (0.6, 1.5)))
CASE_S = 110


def dispatch(tasks, scratch, *, limit=CASE_S):
    kernel = scratch / "projector.so"
    legacy.compact.orbit_projector.compile_kernel(kernel)
    invoke = legacy.compact.invoke

    def command(args, data, timeout):
        if args[-1] == "edge":
            args[-1] = "gate"
            args[-3] = "/trial/edge.py"
            pp = Path(edge_evidence.__file__)
            bindings = (
                (WORKER, "/trial/edge.py"),
                (pp, f"/worker/tools/pipeline_eval/variants/{pp.name}"),
                (
                    Path(prior.edge.__file__),
                    "/worker/tools/pipeline_eval/variants/compact_tile_interior.py",
                ),
            )
            for path, target in bindings:
                args[-5:-5] = ("--ro-bind", str(path), target)
        return invoke(args, data, timeout)

    def lane(cpu, jobs):
        return [
            dict(legacy.run_one(job, kernel, cpu, mode, limit), mode=mode) for job, mode in jobs
        ]

    with (
        patch.object(legacy, "METHODS", legacy.METHODS | {"edge": METHOD}),
        patch.object(legacy.compact, "invoke", command),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        futures = [pool.submit(lane, cpu, tasks[i :: len(CPUS)]) for i, cpu in enumerate(CPUS)]
        return [row for future in futures for row in future.result()]


def diagnose(public, scratch):
    captures = _read(prior.REPORT / "public-captures.json")
    sites = list(prior.jobs(public, captures))
    known = _read(prior.REPORT / "scores.json")["rows"]
    by_case = {r["id"]: r for r in known if r["method"] == prior.METHOD and r["arm"] == "c0"}
    rejected_site = next(
        r["site"]
        for r in by_case.values()
        if r["role"] == "near-inside" and r["status"] == "withheld"
    )
    candidates = [
        row
        for panel, _ in sites
        for row in panel
        if row[0]["capture_id"] == rejected_site
        and by_case[row[0]["id"]]["role"].startswith("near-")
    ]
    save_json(
        scratch / "diagnostic-source-lock.json",
        {_p.name: _sha(_p) for _p in (Path(edge_evidence.__file__), WORKER, Path(__file__))},
    )
    save_json(scratch / "diagnostics.json", dispatch([(p, "edge") for p in candidates], scratch))


def prior_context():
    # Bind the three earlier continental sites in addition to all prior simulation strata.
    old, used = ORIGINAL_PRIOR_CONTEXT()
    labels = _read(prior.REPORT / "released-labels.json")
    draws = _read(prior.REPORT / "public-captures.json")
    for key, r in labels.items():
        old.add(tuple(r["location"]))
        used.update((r["trajectory"]["sha256"], draws[key]["source"]["sha256"]))
    return old, used


def fresh(root, output):
    started = perf_counter()
    if (output / "prediction-lock.json").exists():
        raise ValueError("a fresh prediction seal already exists")
    paths = (
        WORKER,
        Path(__file__),
        Path(edge_evidence.__file__),
        Path(prior.__file__),
        Path(prior.edge.__file__),
        legacy.WORKER,
        Path(legacy.rule.__file__),
        Path(legacy.compact.v5_secant_fit.__file__),
        output / "PROTOCOL.md",
    )
    save_json(
        output / "source-lock.json",
        legacy.compact.portable.source_lock()
        | {(str(p) if p.name == "edge_evidence.py" else p.name): _sha(p) for p in paths},
    )
    with patch.multiple(prior, SITES=SITES, prior_context=prior_context):
        captures = list(prior.draw(root, [secrets.token_bytes(32) for _ in SITES]))
    panels = list(prior.jobs(root, captures))
    # A genuine independent stock far control and a shifted authentic containing tile.
    roof, original, history, objects, _, stock = legacy.compact.portable.authentic_roof()
    measured = legacy.compact.ROOF
    prior_roof = _read(legacy.compact.REPORT / "requests.json")
    roof_plan = next(r for r in prior_roof if r["id"] == measured)
    del original, stock
    roof_job = legacy.compact.bound_job(roof_plan, roof, roof_plan["tile"], history, objects)
    if roof_job[0] != roof_plan:
        raise ValueError("measured native and tile binding changed")
    tasks = [(roof_job, "edge"), (panels[0][0][-1], "control")]
    tasks.extend((p, "edge") for panel, _ in panels for p in panel)
    plan = [dict(job[0], mode=mode) for job, mode in tasks]
    save_json(output / "requests.json", plan)
    save_json(
        output / "history.json",
        {capture: p[1] for capture, p in zip(captures, panels, strict=True)},
    )
    hashes = {
        str(f.relative_to(root)): _sha(f)
        for d in ("private", "public")
        for f in sorted((root / d).iterdir())
    }
    save_json(output / "input-lock.json", hashes)
    rows = dispatch(tasks, root)
    if any(_sha(root / name) != sha for name, sha in hashes.items()):
        raise ValueError("private or public inputs changed after lock")
    save_json(output / "predictions.json", rows)
    names = (
        "predictions.json",
        "source-lock.json",
        "requests.json",
        "history.json",
        "input-lock.json",
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            files={name: _sha(output / name) for name in names},
            wall_s=perf_counter() - started,
        ),
    )
    for name, directory in (
        ("released-labels.json", "private"),
        ("public-captures.json", "public"),
    ):
        save_json(output / name, {c: _read(root / directory / f"{c}.json") for c in captures})


ORIGINAL_PRIOR_CONTEXT = prior.prior_context

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--diagnose", type=Path)
    opts = cli.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        cli.error("pin to the three authorized worker lanes")
    root = local_output(opts.root)
    if opts.diagnose:
        diagnose(opts.diagnose, root)
    else:
        fresh(root, REPORT)
