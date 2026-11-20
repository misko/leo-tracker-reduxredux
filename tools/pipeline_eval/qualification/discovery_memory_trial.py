"""Compare sparse initial association against the authenticated composed compact worker."""

import argparse
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS
from ..variants import v5_composed_memory, v5_sparse_discovery
from . import composed_memory_trial as composed
from . import working_memory_trial
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/redesign/discovery-memory"
RUNS = composed.RUNS.with_name("discovery-memory")
WORKER = Path(__file__).with_name("discovery_memory_worker.py")
PRIOR_WORKER = composed.WORKER
PRIOR_SEAL = composed.seal
NICE = 10


def source():
    with patch.object(composed, "WORKER", PRIOR_WORKER):
        earlier = PRIOR_SEAL()
    if earlier != json.loads((composed.REPORT / "source-lock.json").read_bytes()):
        raise ValueError("the composed control sources differ from their original lock")
    paths = (Path(__file__), WORKER, Path(v5_sparse_discovery.__file__))
    return dict(
        earlier,
        source=dict(earlier["source"], **{p.name: _sha(p) for p in paths}),
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        comparison_lock_sha256=_sha(composed.REPORT / "prediction-lock.json"),
        nice=NICE,
    )


def reference():
    path = composed.REPORT / "uncapped-positions.jsonl.gz"
    lock = json.loads((composed.REPORT / "prediction-lock.json").read_bytes())
    if lock["cases"] != [composed.CASE] or _sha(path) != lock["files"][path.name]:
        raise ValueError("composed comparison prediction archive differs")
    return json.loads(gzip.decompress(path.read_bytes()))


def same_science(control, candidate):
    for field in ("id", "input_sha256", "native_sha256", "catalog_sha256", "tile", "detector"):
        if control[field] != candidate[field]:
            raise ValueError(f"candidate has a different scientific input field {field}")
    a, b = control["result"], candidate["result"]
    result = dict(control_status=a["status"], candidate_status=b["status"])
    if a["status"] != "ok" or b["status"] != "ok":
        return result
    s, t = a["metrics"], b["metrics"]
    features = ("conditional_rms_hz", "frequency_score", "associated_observations")
    stages = s["composed_memory_measurement"]["evidence"]
    observed = t["composed_memory_measurement"]["evidence"]
    equal = {stage: observed.get(stage) == value for stage, value in stages.items()}
    equal.update(
        endpoints=a["arms"] == b["arms"],
        recovery_rows=s["bounded_recovery_rows"] == t["bounded_recovery_rows"],
        optimizer_counts={k: v for k, v in s["position_optimizer"].items() if k != "wall_s"}
        == {k: v for k, v in t["position_optimizer"].items() if k != "wall_s"},
        tiled_shortlists=s["tiled_salvage"]["shortlists"] == t["tiled_salvage"]["shortlists"],
    )
    for arm in ARMS:
        for feature in features:
            key = f"{arm}_{feature}"
            equal[key] = s.get(key) == t.get(key)
    return dict(result, equal=equal, exact=all(equal.values()))


def cap(runs, report):
    invoke = composed.subprocess.run

    def low_priority(command, *args, **kwargs):
        if command[0] == "systemd-run":
            command = [command[0], f"--property=Nice={NICE}", *command[1:]]
        elif command[0] == "systemctl":
            command = [*command, "-pNice"]
        return invoke(command, *args, **kwargs)

    with patch.object(composed.subprocess, "run", low_priority):
        composed.memory_cap(runs, report)
    path = report / "memory-cap.json"
    result = json.loads(path.read_bytes())
    result["controls"].append(f"Nice={NICE}")
    save_json(path, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        current = source()
        if path.exists() and json.loads(path.read_bytes()) != current:
            raise ValueError("refuse to replace a previous source seal")
        if not path.exists():
            save_json(path, current)
        return
    with (
        patch.multiple(
            composed, WORKER=WORKER, seal=source, reference=reference, same_science=same_science
        ),
        patch.multiple(
            v5_composed_memory,
            METHOD=v5_sparse_discovery.METHOD,
            BOUNDARY=v5_sparse_discovery.BOUNDARY,
        ),
    ):
        if args.action == "replay":
            if os.getpriority(os.PRIO_PROCESS, 0) != NICE:
                raise ValueError(f"start the unrestricted worker with nice -n {NICE}")
            composed.replay(args.runs, args.report, args.raw)
        elif args.action == "cap":
            cap(args.runs, args.report)
        else:
            composed.publish(args.runs, args.report)


if __name__ == "__main__":
    main()
