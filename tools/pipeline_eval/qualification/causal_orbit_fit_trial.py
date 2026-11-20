"""Replay ten preregistered cases through the three composed numerical guards."""

import argparse
import json
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import validate_result
from ..variants import v5_causal_orbit_fit as candidate
from ..variants import v5_cavity_isolation, v5_lean, v5_optional_cavity
from . import orbit_domain_trial as domain
from . import previous_orbit_trial as prior
from . import projector_roof
from .compact_roof_selection_results import normalize_attempt
from .full_v5_check import _sha
from .optional_cavity_trial import OUT as CAVITY
from .orbit_domain_results import BINDING_FIELDS
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = domain.REPORT.parents[1] / "integration/orbit-repairs"
ORDER = (
    "DS26-0191", "DS26-0199", "DS26-0181", "DS26-0156", "DS26-0281", "DS26-0132",
    "DS26-0285", "DS26-0289", "DS26-0034", "DS26-0126",
)
CASES = tuple(sorted(ORDER))
METHOD = candidate.METHOD
WORK = Path("/tmp/leo-causal-orbit-fit")
CAP_S = 195
CPUS = (0, 1, 2, 3)


def source_lock():
    stock = domain.archived()
    roster = domain.compact.REPORT / "roster.json"
    bindings = json.loads(roster.read_bytes())["bindings"]
    for ident in CASES:
        if (
            any(stock[ident][key] != bindings[ident][key] for key in BINDING_FIELDS)
            or stock[ident]["result"]["status"] != ("ok" if ident in prior.CONTROLS else "failed")
        ):
            raise ValueError(f"{ident} differs from its certified original compact result")
    layers = (candidate, domain.v5_orbit_domain, prior.v5_previous_orbit,
              v5_cavity_isolation, v5_optional_cavity)
    files = (domain.REPORT / "prediction-lock.json", prior.REPORT / "prediction-lock.json",
             CAVITY / "figure-lock.json", domain.COMPLETION / "all32-prediction-lock.json")
    expected_sources = {
        domain.v5_orbit_domain: json.loads((domain.REPORT / "source-lock.json").read_bytes())[
            "variant_sha256"
        ],
        prior.v5_previous_orbit: json.loads((prior.REPORT / "source-lock.json").read_bytes())[
            "worker_sha256"
        ],
    }
    if any(_sha(Path(module.__file__)) != value for module, value in expected_sources.items()):
        raise ValueError("the composed orbit guards differ from their standalone sources")
    confirmed = CAVITY / "confirmed.jsonl.gz"
    cavity = json.loads((CAVITY / "figure-lock.json").read_bytes())
    if _sha(confirmed) != cavity["files"][confirmed.name] or any(
        row["corrected_source"]["adapter"] != _sha(Path(v5_cavity_isolation.__file__))
        or row["corrected_source"]["original"]["files"]["v5_optional_cavity.py"]
        != _sha(Path(v5_optional_cavity.__file__))
        for row in read_predictions(confirmed).values()
    ):
        raise ValueError("the corrected cavity worker differs from its standalone confirmation")
    return dict(
        method=METHOD, cases=list(CASES), launch_order=list(ORDER), pinned_cpus=list(CPUS), nice=10,
        worker_limit_s=CAP_S, overall_limit_s=600,
        bindings={key: bindings[key] for key in CASES},
        locked_workers={Path(m.__file__).name: _sha(Path(m.__file__)) for m in layers},
        runner_sha256=_sha(Path(__file__)), protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        original_roster_sha256=_sha(roster),
        compact_dependencies=domain.secant_confirmation.frozen_sources(),
        scientific_source=v5_lean.SOURCE_SHA256,
        comparator_locks_sha256={p.parent.name: _sha(p) for p in files},
    )


def _worker(work, case, baseline, binding, cpu, seal):
    os.sched_setaffinity(0, {cpu})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.setpriority(os.PRIO_PROCESS, 0, 10)
    ident = case["id"]
    if (
        projector_roof.input_hash(case) != binding["input_sha256"]
        or _sha(Path(case["request_path"])) != binding["prepared_request_sha256"]
        or _sha(Path(case["native_path"])) != binding["native_sha256"]
        or _sha(Path(case["catalog_path"])) != binding["catalog_sha256"]
        or case["regions"] != [binding["tile"]]
    ):
        raise ValueError(f"{ident} differs from its frozen native localization request")
    v5_lean.TIMEOUT_S = CAP_S
    wall, cpu_start = perf_counter(), cpu_s()
    root = work / ident
    result = candidate.run(case, root)
    timing = stamp(wall, cpu_start)
    row = normalize_attempt(dict(
        id=ident, **{key: baseline[key] for key in BINDING_FIELDS}, method=METHOD,
        source="fresh-composed-compact", mode="matched-tile", cpu=cpu, source_lock_sha256=seal,
        attempted=True, worker_returned=True, result=result, attempt_resource=timing,
        worker_wall_s=result["metrics"].get("candidate_s", timing["wall_s"]),
    ))
    validate_result(result)
    save_json(root / "prediction.json", row)
    print(ident, result["status"], result.get("reason"), row["worker_wall_s"], flush=True)


def replay(work, case_path):
    path = REPORT / "source-lock.json"
    lock = json.loads(path.read_bytes())
    if lock != source_lock():
        raise ValueError("composed sources or scientific request changed before replay")
    work.mkdir(parents=True, exist_ok=False)
    cases = json.loads(case_path.read_bytes())
    original, digest = domain.archived(), _sha(path)
    pending = iter(ORDER)
    clock = perf_counter()
    with ProcessPoolExecutor(max_workers=4, max_tasks_per_child=1) as pool:
        def submit(ident, cpu):
            return pool.submit(
                _worker, work, cases[ident], original[ident], lock["bindings"][ident], cpu, digest
            )

        tasks = {submit(next(pending), cpu): cpu for cpu in CPUS}
        while tasks:
            done, _ = wait(tasks, return_when=FIRST_COMPLETED)
            for task in done:
                cpu = tasks.pop(task)
                task.result()
                ident = next(pending, None)
                if ident is not None and perf_counter() - clock + CAP_S + 5 < 600:
                    tasks[submit(ident, cpu)] = cpu
    if lock != source_lock():
        raise ValueError("composed sources or scientific request changed during replay")
    save_json(work / "runtime.json", dict(wall_s=perf_counter() - clock, worker_limit_s=CAP_S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "replay"))
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--cases", type=Path, default=prior.CACHE)
    args = parser.parse_args()
    if args.stage == "freeze":
        path = REPORT / "source-lock.json"
        if path.exists():
            raise ValueError("composed receiver is already registered")
        save_json(path, source_lock())
    else:
        replay(local_output(args.work), args.cases)


if __name__ == "__main__":
    main()
