"""Replay the second whole-IQ cavity and publish the matched service evidence."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, references, save_json, write
from . import whole_cavity as cavity
from . import whole_cavity_scores as scoring
from . import whole_cavity_worker as worker
from . import whole_memory_chain as apparatus
from .full_v5_check import _sha
from .prefix_figures import csv_file

CASES = ("DS26-0036", "DS29-0082")
FRESH = CASES[1]
REPORT = apparatus.ROOT / "reports/2026_11_19_receiver_screening/streamlined/whole-pair"
RUNS = apparatus.RUNS.with_name("whole-pair")


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def preseal():
    earlier_source = cavity.REPORT / "source-lock.json"
    earlier = cavity.plan()
    if json.loads(earlier_source.read_bytes()) != earlier:
        raise ValueError("the DS26 whole-cavity decoder or numerical source changed")
    with patch.multiple(apparatus, control=cavity.PREVIOUS_CONTROL, chain=cavity.RAW):
        raw = cavity.PREVIOUS_PLAN()
    old_position = apparatus.sealed(cavity.REPORT, "positions.jsonl.gz")
    old_stages = apparatus.sealed(cavity.REPORT, "stages.json.gz")
    old_compare = apparatus.sealed(cavity.REPORT, "comparison.json")
    full_recovery = apparatus.sealed(apparatus.REPORT, "positions.jsonl.gz")
    recorded, recovered = map(read_gzip, (old_position, full_recovery))
    previous = read_gzip(old_stages)[CASES[0]]
    if (
        (recorded["id"], recovered["id"]) != CASES
        or recorded["method"] != worker.METHOD
        or recorded["result"]["status"] != "ok"
        or recovered["result"]["status"] != "ok"
        or not json.loads(old_compare.read_bytes())["exact"]
        or previous["position"]["end"]["memory.max"] != worker.MEMORY
        or previous["position"]["end"]["memory.swap.max"] != 0
    ):
        raise ValueError("previous whole-IQ evidence cannot serve as the paired control")
    inputs = {}
    same_ordinary = apparatus.sealed(apparatus.PRIOR, "positions.jsonl.gz")
    for ident in CASES:
        row, oracle = raw["inputs"][ident], cavity.control(ident)
        if oracle["native_sha256"] != row["native_sha256"] or oracle["result"]["status"] != "ok":
            raise ValueError("missing successful same-ordinary archived cavity")
        inputs[ident] = dict(
            row, control_method=oracle["method"], control_sha256=_sha(same_ordinary)
        )
    paths = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        earlier_source,
        old_position,
        old_stages,
        old_compare,
        full_recovery,
    )
    return dict(
        earlier,
        inputs=inputs,
        source_ds26_prediction_lock_sha256=_sha(cavity.REPORT / "prediction-lock.json"),
        fresh=FRESH,
        sources=dict(earlier["sources"]) | {str(path): _sha(path) for path in paths},
    )


def publish(runs, report):
    saved = json.loads((runs / "plan.json").read_bytes())
    if preseal() != saved:
        raise ValueError("whole-pair sources or inputs differ from the preflight lock")
    with patch.multiple(apparatus, chain=worker, control=cavity.control):
        latest, trace = apparatus.summarize(runs, FRESH)
    first = read_gzip(apparatus.sealed(cavity.REPORT, "positions.jsonl.gz"))
    results = (first, latest)
    all_stages = read_gzip(apparatus.sealed(cavity.REPORT, "stages.json.gz"))
    all_stages[FRESH] = trace
    compare = {row["id"]: scoring.comparison(row) for row in results}
    save_json(report / "source-lock.json", saved)
    save_json(report / "comparison.json", compare)
    write(
        report / "positions.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in results), mtime=0),
    )
    write(report / "stages.json.gz", gzip.compress(encoded(all_stages), mtime=0))
    files = ("positions.jsonl.gz", "stages.json.gz", "comparison.json")
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(CASES),
            files={f: _sha(report / f) for f in files},
            source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )
    truth = {r["id"]: r["truth"] for r in references("roof16", CASES)[1]}
    csv_file(
        report / "scores.csv",
        [s for row in results for s in scoring.arm_scores(row, truth[row["id"]])],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "publish"))
    parser.add_argument("--runs", type=local_output, default=RUNS)
    args = parser.parse_args()
    if args.action == "seal":
        args.runs.mkdir(parents=True, exist_ok=False)
        save_json(args.runs / "plan.json", preseal())
    elif args.action == "run":
        with patch.multiple(apparatus, chain=worker, control=cavity.control, plan=preseal):
            apparatus.run(FRESH, args.runs)
    else:
        publish(args.runs, REPORT)


if __name__ == "__main__":
    main()
