"""Qualify original complete-family nomination on contiguous orbit tiles."""

import argparse
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import v5_composed_memory, v5_lean, v5_nomination_memory
from ..variants import v5_signed_context_memory as signed
from . import composed_memory_trial as apparatus
from . import discovery_memory_trial as discovery
from . import signed_context_memory_trial as previous
from . import working_memory_trial
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/deployment/nomination-memory"
RUNS = previous.RUNS.with_name("nomination-memory")
WORKER = Path(__file__).with_name("nomination_memory_worker.py")
STOCK = Path(__file__).with_name("nomination_memory_stock_worker.py")
CPU, STOCK_CPU = 17, 18


def source():
    path = previous.REPORT / "source-lock.json"
    with patch.object(apparatus, "CPU", CPU):
        earlier = previous.source()
    if json.loads(path.read_bytes()) != earlier:
        raise ValueError("the signed-context control differs from its original lock")
    frozen = v5_lean.SOURCE / "leo/analysis"
    paths = (
        Path(__file__),
        WORKER,
        STOCK,
        Path(v5_nomination_memory.__file__),
        REPORT / "PROTOCOL.md",
        frozen / "localization_v3/family_cavity.py",
        frozen / "localization_v3/cavity_prediction.py",
        frozen / "research/orbit_phase_geometry.py",
    )
    return dict(
        source={p.name: _sha(p) for p in paths},
        prior_source_sha256=_sha(path),
        prior_predictions_sha256=_sha(previous.REPORT / "prediction-lock.json"),
        case=apparatus.CASE,
        cpu=CPU,
        stock_cpu=STOCK_CPU,
        nice=discovery.NICE,
        tile_rows=v5_nomination_memory.TILE,
        memory_max_bytes=apparatus.MEMORY,
    )


def reference():
    lock = json.loads((previous.REPORT / "prediction-lock.json").read_bytes())
    path = previous.REPORT / "uncapped-positions.jsonl.gz"
    if lock["cases"] != [apparatus.CASE] or _sha(path) != lock["files"][path.name]:
        raise ValueError("signed-context prediction archive differs from its lock")
    return json.loads(gzip.decompress(path.read_bytes()))


def nomination_parity(stock, candidate):
    metrics = [r["result"]["metrics"]["nomination_memory"] for r in (stock, candidate)]
    a, b = metrics

    def science(item):
        return {k: v for k, v in item.items() if k != "grid_payload_bytes"}

    checks = dict(
        ordered_coarse=[science(item) for item in a["coarse"]]
        == [science(item) for item in b["coarse"]],
        complete_nominations=bool(a["nominations"]) and a["nominations"] == b["nominations"],
        calibrated_science=discovery.same_science(stock, candidate).get("exact", False),
    )
    return dict(checks=checks, exact=all(checks.values()), stock=a, tiled=b)


def parity(runs):
    paths = runs / "stock/uncapped/prediction.json", runs / "uncapped/prediction.json"
    stock, candidate = (json.loads(path.read_bytes()) for path in paths)
    result = nomination_parity(stock, candidate)
    if not discovery.same_science(reference(), stock).get("exact", False):
        raise ValueError("the fresh dense nomination control changed scientific output")
    if not result["exact"]:
        print(json.dumps(result, indent=2), flush=True)
        raise ValueError("the row-bounded nomination differs from the matched dense reference")
    return stock, result


def publish(runs, report):
    stock, evidence = parity(runs)
    path = report / "fresh-control-positions.jsonl.gz"
    write(path, gzip.compress(encoded(stock) + b"\n", mtime=0))
    save_json(report / "nomination-parity.json", evidence)
    apparatus.publish(runs, report)
    lock = report / "prediction-lock.json"
    manifest = json.loads(lock.read_bytes())
    for name in ("fresh-control-positions.jsonl.gz", "nomination-parity.json"):
        manifest["files"][name] = _sha(report / name)
    save_json(lock, manifest)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "stock", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    if args.action == "seal":
        path, candidate = args.report / "source-lock.json", source()
        if path.exists() and json.loads(path.read_bytes()) != candidate:
            raise ValueError("refuse to replace a previous source seal")
        if not path.exists():
            save_json(path, candidate)
        return
    stock = args.action == "stock"
    method = signed if stock else v5_nomination_memory
    with (
        patch.multiple(
            apparatus,
            WORKER=STOCK if stock else WORKER,
            CPU=STOCK_CPU if stock else CPU,
            seal=source,
            reference=reference,
            same_science=discovery.same_science,
        ),
        patch.multiple(v5_composed_memory, METHOD=method.METHOD, BOUNDARY=method.BOUNDARY),
    ):
        if args.action in ("replay", "stock"):
            if os.getpriority(os.PRIO_PROCESS, 0) != discovery.NICE:
                raise ValueError(f"start both unrestricted workers with nice -n {discovery.NICE}")
            apparatus.replay(args.runs / "stock" if stock else args.runs, args.report, args.raw)
        elif args.action == "cap":
            parity(args.runs)
            discovery.cap(args.runs, args.report)
        else:
            publish(args.runs, args.report)


if __name__ == "__main__":
    main()
