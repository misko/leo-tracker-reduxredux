"""Score sealed paired normal memo replays and their whole-worker resource deltas."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from .. import corpus
from ..__main__ import save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import phase_cache_confirmation as trial
from . import row_memory_replay
from .cavity_lifetime_results import MATCH, statistics
from .full_receiver_comparison import read, sha
from .portable_gate_trials import compressed_rows

OUT = trial.OUT
MEMO = trial.METHODS["memo"]
STOCK = trial.METHODS["ordinary"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    seal = read(OUT / "prediction-lock.json")
    for filename, expected in seal["files"].items():
        assert sha(OUT / filename) == expected
    data = list(
        map(json.loads, gzip.decompress((OUT / "paired.jsonl.gz").read_bytes()).splitlines())
    )
    assert len(data) == 2 * len(seal["cases"])
    plan = read(OUT / "plan.json")["source"]
    _, control = row_memory_replay.controls()
    compact = control[row_memory_replay.baseline.COMPACT]
    targets = {r["id"]: r["truth"] for r in corpus.references("roof16")}
    targets.update((r["id"], r["truth"]) for r in corpus.references("ds26-all159"))
    position, score, pairs, backend = [], [], [], []
    for ident in seal["cases"]:
        group = {r["method"]: r for r in data if r["id"] == ident}
        assert group.keys() == {STOCK, MEMO}
        group[compact[ident]["method"]] = compact[ident]
        detail = dict(id=ident, methods={})
        for method, entry in group.items():
            assert all(entry[k] == plan["inputs"][ident][k] for k in MATCH)
            result = entry["result"]
            position.append({k: v for k, v in entry.items() if k != "samples"})
            resource = statistics(entry, [])
            detail["methods"][method] = dict(
                status=result["status"],
                terminal=entry.get("terminal"),
                reason=result.get("reason"),
                wall_s=entry.get("worker_wall_s"),
                stages=result["metrics"].get("stage_s"),
                native_memo=result["metrics"].get("native_normal_memo"),
                cpu_s=resource.get("terminal_cpu_s"),
                peak_mib=resource.get("observed_peak_mib"),
                reported_peak_mib=resource.get("terminal_peak_mib"),
                max_sampled_anon_mib=resource.get("max_sampled_anon_mib"),
                max_sampled_file_mib=resource.get("max_sampled_file_mib"),
            )
            if method in (STOCK, MEMO) and result["status"] == "ok":
                path = args.work / entry["mode"] / ident / "receipts/native"
                (receipt,) = path.glob("*.json")
                value = read(receipt)
                num = result["metrics"]["native_normal_memo"]
                assert value["counts"]["calls"] == num["native_calls"]
                backend.append(dict(id=ident, method=method, digest=sha(receipt), receipt=value))
            for arm in ARMS:
                pred = result["arms"][arm]
                score.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        published=pred["latlon"] is not None,
                        status=result["status"],
                        position_error_km=distance_km(pred["latlon"], targets[ident]),
                        rf_rms_hz=pred.get("rf_rms_hz"),
                        identical_unrestricted=pred == compact[ident]["result"]["arms"][arm],
                    )
                )
        stock, memo = (detail["methods"][k] for k in (STOCK, MEMO))
        detail["whole_delta"] = {
            k: memo[k] - stock[k] if memo[k] is not None and stock[k] is not None else None
            for k in ("wall_s", "cpu_s", "peak_mib")
        }
        pairs.append(detail)
    cohorts = defaultdict(list)
    for r in score:
        cohorts[r["method"], r["arm"]].append(r)
    summary = {
        "/".join(key): dict(
            scheduled=len(rows),
            published=sum(r["published"] for r in rows),
            position_error_km=distribution(r["position_error_km"] for r in rows),
            rf_rms_hz=distribution(r["rf_rms_hz"] for r in rows),
        )
        for key, rows in cohorts.items()
    }
    archives = OUT / "positions.jsonl.gz", OUT / "scores.json"
    write(archives[0], compressed_rows(position))
    save_json(archives[1], dict(pairs=pairs, arms=score, summary=summary))
    execution = OUT / "native-backend-receipts.json"
    save_json(execution, backend)
    files = (*archives, OUT / "plan.json", OUT / "prediction-lock.json", execution)
    save_json(
        OUT / "figure-lock.json", dict(cases=seal["cases"], files={p.name: sha(p) for p in files})
    )


if __name__ == "__main__":
    main()
