"""Repeat only the peak-path candidate under the declared elapsed-time gap policy."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, save_json
from . import peak_paths_trial as initial
from .armijo_finish_results import pack

OUT = initial.OUTPUT


def run(work):
    old = initial.read(OUT / "first-pass/prediction-lock.json")
    initial.archive.base.secant_full._verify_files(OUT / "first-pass", old["files"])
    rows, stock = initial.bindings()
    if rows != initial.read(OUT / "first-pass/blind-plan.json")["frames"]:
        raise ValueError("the revised decoder requires the same frozen source visits and offers")
    source = initial.sources()["peak_paths"]
    tracked = (Path(__file__), Path(initial.__file__), *source[0], OUT / "ELAPSED-BRIDGE.md")
    frozen = {str(f.relative_to(ROOT)): initial.digest(f.read_bytes()) for f in tracked}
    work.mkdir(parents=True, exist_ok=False)
    save_json(
        OUT / "elapsed-plan.json",
        dict(
            frames=rows,
            sources=frozen,
            first_pass_sha256=initial.digest(
                (OUT / "first-pass/prediction-lock.json").read_bytes()
            ),
            reference_plan_sha256=stock,
        ),
    )
    start = perf_counter()
    remaining = 600 - old["wall_s"] - 10

    def lane(i):
        for q in rows[i :: len(initial.CPUS)]:
            row = initial.attempt(
                q,
                "peak_paths",
                initial.CPUS[i],
                source,
                perf_counter() - start < remaining - initial.CAP,
            )
            save_json(work / (q["id"] + ".json"), row)

    with ThreadPoolExecutor(len(initial.CPUS)) as engine:
        list(engine.map(lane, range(len(initial.CPUS))))
    if {str(f.relative_to(ROOT)): initial.digest(f.read_bytes()) for f in tracked} != frozen:
        raise ValueError("elapsed forecast source changed during measurement")
    measured = [initial.read(work / (row["id"] + ".json")) for row in rows]
    traces = [dict(id=r["id"], selected_paths=r.pop("trace")) for r in measured if "trace" in r]
    files = {
        "positions.jsonl.gz": pack(
            OUT, "positions.jsonl.gz", [p for p in measured if not p["shuffle"]]
        ),
        "shuffle-position.jsonl.gz": pack(
            OUT, "shuffle-position.jsonl.gz", [p for p in measured if p["shuffle"]]
        ),
        "path-traces.jsonl.gz": pack(OUT, "path-traces.jsonl.gz", traces),
        "folded-positions.jsonl.gz": initial.digest(
            (OUT / "folded-positions.jsonl.gz").read_bytes()
        ),
        "elapsed-plan.json": initial.digest((OUT / "elapsed-plan.json").read_bytes()),
    }
    save_json(
        OUT / "prediction-lock.json",
        dict(
            files=files,
            wall_s=perf_counter() - start,
            attempts=len(rows),
            first_pass_wall_s=old["wall_s"],
            cases=[r["id"] for r in rows],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    run(parser.parse_args().work)
