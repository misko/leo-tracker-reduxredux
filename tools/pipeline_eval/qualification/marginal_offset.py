"""Replay source-fixed Gaussian component offsets on case-matched native recordings."""

import argparse
import ast
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import marginal_offset as variant
from ..variants.v5_lean import SOURCE as V5_SOURCE
from . import native_joint_full as full
from . import native_joint_trial as base
from .native_lean_eval import _write_predictions

REPORT = full.REPORT.parent.parent / "refinement/marginal-offset"
WORKER = Path(__file__).with_name("marginal_offset_worker.py")
PRIOR_SOURCE = "leo/analysis/research/retained_track_likelihood.py"
SALT = "marginal-track-constant-v1:"
TARGETS = ("DS26-0197", "DS29-0316", "DS26-0036", "DS29-0082")
CPUS = (0, 7, 17)
FILES = ("positions.jsonl.gz", "stock-positions.jsonl.gz")
BINDINGS = ("native_sha256", "catalog_sha256", "input_sha256", "observation_sha256")
OWNERSHIP = (
    "training_ownership",
    "held_ownership",
    "final_c0_ownership",
    "final_fitted_c_ownership",
)


def prepare():
    inputs = base.phase.frozen_inputs()

    def salted(ident):
        return corpus._sha((SALT + ident).encode())

    confirmation = [
        ident
        for prefix in ("DS26", "DS29")
        for ident in sorted(
            (i for i in inputs if i.startswith(prefix) and i not in TARGETS), key=salted
        )[:3]
    ]
    jobs = [
        full.query(inputs[i], group)
        for group, ids in (("diagnostic", TARGETS), ("confirmation", confirmation))
        for i in ids
    ]
    jobs.extend(sorted(full.omitted_controls(inputs), key=lambda job: salted(job[0]["id"]))[:3])
    return jobs


def sources(bundle):
    path = V5_SOURCE / PRIOR_SOURCE
    parsed = ast.parse(path.read_bytes())
    (sigma,) = [
        ast.literal_eval(node.value)
        for node in parsed.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "BIAS" for t in node.targets)
    ]
    if sigma != variant.SIGMA_HZ:
        raise ValueError("the pinned v5 Gaussian component scale differs")
    files = (Path(__file__), WORKER, Path(variant.__file__), Path(variant.fixed.__file__))
    return dict(
        ancestor=base.sources(bundle),
        files={str(p.relative_to(corpus.REPO)): base.phase.digest(p) for p in files},
        prior_source=PRIOR_SOURCE,
        prior_source_sha256=base.phase.digest(path),
        sigma_hz=sigma,
    )


def command(cpu, paths, bundle):
    argv = base.command(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    for module in (variant, variant.fixed):
        path = Path(module.__file__)
        argv[-3:-3] = ["--ro-bind", str(path), f"/worker/tools/pipeline_eval/variants/{path.name}"]
    return argv


def attempt(query, paths, archive, cpu, bundle, sigma):
    ident, packet = query["id"], query["packet"]
    request = corpus._sha(encoded(packet))
    if request != archive["input_sha256"]:
        raise ValueError(f"{ident} input differs from its archived receiver query")
    clock = perf_counter()
    try:
        proc = subprocess.run(
            command(cpu, paths, bundle),
            input=encoded(dict(packet, component_sigma_hz=sigma)),
            capture_output=True,
            timeout=60,
            check=True,
        )
        receipt = json.loads(proc.stdout)
    except (ValueError, subprocess.SubprocessError) as error:
        stderr = (getattr(error, "stderr", None) or b"").decode(errors="replace")
        receipt = dict(
            result=dict(
                status="timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed",
                reason=stderr[-2000:] or str(error),
                boundary=variant.BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None) for arm in ARMS},
            )
        )
    receipt.update(
        id=ident,
        recording=query["recording"],
        cohort=query["cohort"],
        method=variant.METHOD if sigma else variant.STOCK,
        input_sha256=request,
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
        cpu=cpu,
        worker_wall_s=perf_counter() - clock,
    )
    for key in (*BINDINGS, "tile"):
        if key in receipt and receipt[key] != archive[key]:
            raise ValueError(f"{ident} changed its archived {key}")
    validate_result(receipt["result"])
    print(
        ident,
        receipt["method"],
        receipt["result"]["status"],
        receipt["result"]["reason"],
        flush=True,
    )
    return receipt


def run(work, bundle, out):
    work, out = local_output(work), local_output(out)
    work.mkdir(parents=True, exist_ok=False)
    frozen = sources(bundle)
    jobs = prepare()
    plan = dict(cases=[row for row, _ in jobs], salt=SALT, source=frozen, cpus=CPUS)
    save_json(work / "plan.json", plan)
    lock_path = full.REPORT / "prediction-lock.json"
    lock = base.phase._read(lock_path)
    base.secant_full._verify_files(full.REPORT, lock["files"])
    with gzip.open(full.REPORT / "positions.jsonl.gz", "rt") as stream:
        archive = {row["id"]: row for row in map(json.loads, stream)}

    def lane(cpu, tasks):
        for index, (query, paths) in tasks:
            prior = archive[query["id"]]
            flags = (0.0, variant.SIGMA_HZ) if index % 2 == 0 else (variant.SIGMA_HZ, 0.0)
            for sigma in flags:
                row = attempt(query, paths, prior, cpu, bundle, sigma)
                save_json(work / f"{row['id']}-{row['method']}.json", row)

    start = perf_counter()
    indexed = list(enumerate(jobs))
    with ThreadPoolExecutor(len(CPUS)) as pool:
        futures = [pool.submit(lane, cpu, indexed[i :: len(CPUS)]) for i, cpu in enumerate(CPUS)]
        for future in futures:
            future.result()
    if sources(bundle) != frozen:
        raise ValueError("the isolated component fit sources changed during replay")
    names = [row["id"] for row, _ in jobs]
    for filename, method in zip(FILES, (variant.METHOD, variant.STOCK), strict=True):
        _write_predictions(
            out / filename, [base.phase._read(work / f"{i}-{method}.json") for i in names]
        )
    save_json(out / "source-lock.json", frozen)
    save_json(out / "plan.json", plan)
    files = {
        name: base.phase.digest(out / name) for name in (*FILES, "source-lock.json", "plan.json")
    }
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=names,
            files=files,
            native_archive_lock_sha256=base.phase.digest(lock_path),
            wall_s=perf_counter() - start,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", default=REPORT, type=Path)
    parser.add_argument("--bundle", default=base.BUNDLE, type=Path)
    args = parser.parse_args()
    run(args.work, args.bundle, args.out)


if __name__ == "__main__":
    main()
