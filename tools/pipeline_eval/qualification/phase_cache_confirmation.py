"""Compare fresh compact lifetime workers with the exact one-entry normal memo."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic
from types import FunctionType

from ..__main__ import local_output, save_json, write
from ..variants import v5_phase_cache
from . import cavity_lifetime_trial as parent
from .full_receiver_comparison import read, sha
from .phase_cache_trial import OUT as REPORT
from .portable_gate_trials import compressed_rows

OUT = REPORT / "confirmation"
WORKER = Path(__file__).with_name("phase_cache_worker.py")
METHODS = {"ordinary": parent.MODES["direct"], "memo": v5_phase_cache.METHOD}
SALT = "phase-cache-confirm-v1:"


def lock():
    base = read(parent.OUT / "plan.json")
    assert base["source"] == parent.source()
    inputs = base["source"]["inputs"]
    ids = sorted(
        (i for i in base["source"]["cases"] if i != "DS29-0316"),
        key=lambda i: sha256((SALT + inputs[i]["native_sha256"]).encode()).hexdigest(),
    )
    sources = {
        p.name: sha(p)
        for p in (
            WORKER,
            Path(__file__),
            Path(v5_phase_cache.__file__),
            REPORT / "PROTOCOL.md",
            REPORT / "profile.json",
            REPORT / "profile-run.json",
            parent.OUT / "plan.json",
        )
    }
    return dict(
        source=base["source"]
        | dict(cases=ids, cpu_by_id=dict(zip(ids, (20, 21, 22), strict=True))),
        experiment=sources,
        profile_id="DS29-0316",
        salt=SALT,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = local_output(args.work)
    plan = lock()
    path = OUT / "plan.json"
    if path.exists():
        raise FileExistsError(path)
    save_json(path, plan)
    globals_for_exec = dict(parent.execute.__globals__, WORKER=WORKER, OUT=OUT, MODES=METHODS)
    execute = FunctionType(parent.execute.__code__, globals_for_exec)
    start = monotonic()

    def lane(i, ident):
        modes = ("memo", "ordinary") if i % 2 else ("ordinary", "memo")
        return [execute(plan, work / m, ident, m) for m in modes]

    jobs = list(enumerate(plan["source"]["cases"]))
    with ThreadPoolExecutor(3) as pool:
        tasks = [pool.submit(lane, i, ident) for i, ident in jobs]
        records = [r for task in tasks for r in task.result()]
    assert plan == lock()
    raw = OUT / "paired.jsonl.gz"
    write(raw, compressed_rows(records))
    save_json(
        OUT / "prediction-lock.json",
        dict(
            cases=plan["source"]["cases"],
            files={p.name: sha(p) for p in (raw, path)},
            wall_s=monotonic() - start,
        ),
    )


if __name__ == "__main__":
    main()
