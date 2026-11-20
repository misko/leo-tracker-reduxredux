"""Paired, single-core native replays for the scalar Doppler noise model."""

import argparse
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import innovation_noise
from . import native_joint_full as panel
from .armijo_finish_results import pack
from .secant_fit_trial import failed_result

base = panel.base
phase = base.phase
REPORT = panel.REPORT.parents[1] / "refinement/innovation-noise"
WORKER = Path(__file__).with_name("innovation_noise_worker.py")
METHOD = "native_innovation_noise"
SALT = "innovation-filter-20261119/"
PRIMARY = ("DS26-0036", "DS29-0082", "DS26-0223", "DS29-0316")
CPU = 19
CAP = 12 * 60
stock_command = base.command


def choose(jobs):
    entries = {q["id"]: (q, paths) for q, paths in jobs}
    order = sorted(entries, key=lambda k: phase.corpus._sha((SALT + k).encode()))
    other = [k for k in order if k not in PRIMARY and entries[k][0]["cohort"] == "roof"]
    confirmed = [k for k in other if k.startswith("DS26-")][:6] + [
        k for k in other if k.startswith("DS29-")
    ][:2]
    omitted = [k for k in order if entries[k][0]["cohort"] == "omitted"][:3]
    selected = [*PRIMARY, *confirmed, *omitted]
    if len(selected) != 15 or len(set(selected)) != 15:
        raise ValueError("incomplete prescribed two-region roster")
    return [entries[k] for k in selected]


def command(cpu, paths, bundle):
    cmd = stock_command(cpu, paths, bundle)
    cmd[cmd.index(str(base.WORKER))] = str(WORKER)
    cmd[-3:-3] = [
        "--ro-bind",
        str(Path(innovation_noise.__file__)),
        "/worker/tools/pipeline_eval/variants/innovation_noise.py",
    ]
    return cmd


def source(bundle):
    return dict(
        native=base.sources(bundle),
        filter=phase.digest(Path(innovation_noise.__file__)),
        worker=phase.digest(WORKER),
        runner=phase.digest(Path(__file__)),
        protocol=phase.digest(REPORT / "PROTOCOL.md"),
        reference=phase.digest(panel.REPORT / "prediction-lock.json"),
    )


def run(work, output, bundle):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    plan_roster, all_jobs = panel.prepare(bundle)
    if plan_roster != phase._read(panel.REPORT / "roster.json"):
        raise ValueError("original native roof or omitted roster differs")
    jobs = choose(all_jobs)
    sources = source(bundle)
    plan = dict(source=sources, cases=[q for q, _ in jobs], cpu=CPU, cap_s=CAP, case_cap_s=base.CAP)
    save_json(output / "plan.json", plan)
    started = perf_counter()
    outputs = {METHOD: [], base.METHOD: []}
    for i, (query, paths) in enumerate(jobs):
        pair = [(base.METHOD, stock_command), (METHOD, command)]
        for method, argv in pair if i % 2 == 0 else reversed(pair):
            if perf_counter() - started > CAP - base.CAP - 2:
                packet = query["packet"]
                row = dict(
                    id=query["id"],
                    recording=query["recording"],
                    cohort=query["cohort"],
                    tile=packet["offer"],
                    method=method,
                    input_sha256=phase.corpus._sha(base.encoded(packet)),
                    catalog_sha256=packet["catalogue"]["sha256"],
                    native_sha256=packet["native"]["sha256"],
                    worker_wall_s=None,
                    result=failed_result("missing", "batch deadline before execution"),
                )
            else:
                with patch.object(base, "command", argv), patch.object(base, "METHOD", method):
                    row = base.attempt(query, paths, CPU, bundle)
            outputs[method].append(row)
            save_json(work / f"{method}-{query['id']}.json", row)
    if sources != source(bundle):
        raise ValueError("frozen numerical sources changed during replay")
    files = {"plan.json": phase.digest(output / "plan.json")}
    for method, data in outputs.items():
        filename = f"{method}.jsonl.gz"
        files[filename] = pack(output, filename, data)
    save_json(
        output / "prediction-lock.json",
        dict(cases=[q["id"] for q, _ in jobs], files=files, wall_s=perf_counter() - started),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--bundle", type=Path, default=base.BUNDLE)
    args = parser.parse_args()
    run(args.work, args.output, args.bundle)
