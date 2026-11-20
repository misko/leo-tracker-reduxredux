"""Qualify the prepared-fractional kernel against complete ordinary cavity controls."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, references, save_json, write
from . import fractional_runtime_whole as parity
from . import iq_schedule, whole_cavity, whole_cavity_scores, whole_pair
from . import whole_fractional_worker as worker
from . import whole_memory_chain as apparatus
from .full_v5_check import NATIVE_LIBRARY, _sha
from .prefix_figures import csv_file

REPORT = whole_pair.REPORT.with_name("whole-fractional")
RUNS = whole_pair.RUNS.with_name("whole-fractional")
CASES = ("DS29-0082", "DS26-0036")
STOCK_LANES = {CASES[0]: whole_pair.RUNS / CASES[0], CASES[1]: whole_cavity.RUNS / CASES[1]}
PREFLIGHT = REPORT / "abi-preflight.json"


def control(ident):
    return iq_schedule.control(ident)


def plan():
    parent = whole_pair.preseal()
    if parent != json.loads((whole_pair.REPORT / "source-lock.json").read_bytes()):
        raise ValueError("the full-visit control differs from its frozen source")
    builder = worker.LIBRARY.with_name("build-receipt.json")
    stock_builder = NATIVE_LIBRARY.with_name("build-receipt.json")
    value = json.loads(builder.read_bytes())
    stock_build = json.loads(stock_builder.read_bytes())
    gate = json.loads(PREFLIGHT.read_bytes())
    if (
        _sha(worker.LIBRARY) != worker.LIBRARY_SHA256
        or _sha(builder) != worker.BUILD_SHA256
        or value["abi_version"] != 1
        or value["algorithm_id"] != "wave8-gate314-source-v1"
        or stock_build["abi_version"] != value["abi_version"]
        or stock_build["algorithm_id"] != value["algorithm_id"]
        or gate["binary_sha256"] != worker.LIBRARY_SHA256
        or gate["stock_sha256"] != _sha(NATIVE_LIBRARY)
        or set(gate["cases"]) != set(CASES)
        or not all(v["exact"] for v in gate["cases"].values())
    ):
        raise ValueError("prepared-fractional detector differs from its verified wave8 build")
    for ident, canary in gate["cases"].items():
        proof = canary["receipt"]
        original, candidate = (proof["implementations"][role] for role in ("original", "candidate"))
        if (
            proof["case"] != ident
            or _sha(Path(proof["wrapper"])) != proof["wrapper_sha256"]
            or original["binary"] != gate["stock_sha256"]
            or candidate["binary"] != worker.LIBRARY_SHA256
            or any(item["algorithm_id"] != value["algorithm_id"] for item in (original, candidate))
            or original["capabilities"] != candidate["capabilities"]
            or candidate["capabilities"] != [1, 2, 20, 0, 1, 1, 0]
            or original["payload_sha"] != candidate["payload_sha"]
        ):
            raise ValueError("installed ordinary wrapper or archived wave8 canary differs")
    inputs = {}
    sources = (
        Path(__file__),
        Path(worker.__file__),
        Path(parity.__file__),
        Path(iq_schedule.__file__),
        REPORT / "PROTOCOL.md",
        PREFLIGHT,
        builder,
        stock_builder,
        worker.LIBRARY,
        apparatus.sealed(whole_pair.REPORT, "positions.jsonl.gz"),
        apparatus.sealed(whole_pair.REPORT, "stages.json.gz"),
        whole_pair.REPORT / "prediction-lock.json",
    )
    items = dict(parent["sources"]) | {str(path): _sha(path) for path in sources}
    for ident in CASES:
        matched = parent["inputs"][ident]
        archived = control(ident)
        if (
            archived["result"]["status"] != "ok"
            or archived["native_sha256"] != matched["native_sha256"]
        ):
            raise ValueError("ordinary stock cavity does not match the replay input")
        folder = STOCK_LANES[ident]
        raw = json.loads((folder / "raw-stages.json").read_bytes())
        if raw["native_sha256"] != matched["native_sha256"]:
            raise ValueError("stock recorded raw stream does not match its factor receipt")
        for lane in range(2):
            f = folder / f"replayed-{lane}.jsonl"
            items[str(f)] = _sha(f)
        inputs[ident] = dict(matched, stock_lane_path=str(folder))
    return dict(
        parent,
        recording_order=list(CASES),
        inputs=inputs,
        sources=items,
        detector_sha256=worker.LIBRARY_SHA256,
    )


def publish(runs, report):
    pin = json.loads((runs / "plan.json").read_bytes())
    if plan() != pin:
        raise ValueError("prepared-fractional experiment differs from its source and data lock")
    ids = [candidate for candidate in CASES if (runs / f"{candidate}-service.json").is_file()]
    if not ids:
        raise ValueError("no completed candidate service attempt")
    full_trace = json.loads(
        gzip.decompress(apparatus.sealed(whole_pair.REPORT, "stages.json.gz").read_bytes())
    )
    rows, old, stages, comparison = [], [], {}, {}
    with patch.multiple(apparatus, chain=worker, control=control):
        for ident in ids:
            new, stages[ident] = apparatus.summarize(runs, ident)
            original = control(ident)
            raw = stages[ident]["raw"]
            new["origin_native_sha256"] = original["native_sha256"]
            new["native_sha256"] = raw["native_sha256"] if raw else None
            new["input_sha256"] = new["native_sha256"]
            comparison[ident] = dict(
                factor_parity=raw.get("factor_parity") if raw else None,
                lane_parity=raw.get("lane_parity") if raw else None,
                exact_endpoint_and_rms=stages[ident]["exact_endpoints_and_radio"],
                full_stock=iq_schedule.native_durations(full_trace[ident]),
                candidate=iq_schedule.native_durations(stages[ident]),
            )
            old.append(original)
            rows.append(new)
    save_json(report / "source-lock.json", pin)
    save_json(report / "comparison.json", comparison)
    for name, data in (
        ("positions.jsonl.gz", b"".join(encoded(r) + b"\n" for r in rows)),
        ("control-positions.jsonl.gz", b"".join(encoded(r) + b"\n" for r in old)),
        ("stages.json.gz", encoded(stages)),
    ):
        write(report / name, gzip.compress(data, mtime=0))
    files = (
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "stages.json.gz",
        "comparison.json",
        PREFLIGHT.name,
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=ids,
            files={name: _sha(report / name) for name in files},
            source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )
    truth = {r["id"]: r["truth"] for r in references("roof16", ids)[1]}
    scores = [
        dict(s, method=row["method"])
        for row in (*rows, *old)
        for s in whole_cavity_scores.arm_scores(row, truth[row["id"]])
    ]
    csv_file(report / "scores.csv", scores)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run", "publish"))
    p.add_argument("--case", choices=CASES)
    p.add_argument("--runs", type=local_output, default=RUNS)
    a = p.parse_args()
    if a.action == "seal":
        a.runs.mkdir(parents=True, exist_ok=False)
        save_json(a.runs / "plan.json", plan())
    elif a.action == "run":
        if a.case is None:
            p.error("select a recording")
        with patch.multiple(apparatus, chain=worker, control=control, plan=plan):
            apparatus.run(a.case, a.runs)
    else:
        publish(a.runs, REPORT)


if __name__ == "__main__":
    main()
