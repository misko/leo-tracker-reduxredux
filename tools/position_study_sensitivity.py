"""Refit fixed candidate identities by sample rate and time block."""

import argparse
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from polish_regional_doppler import polish
from replay_regional_doppler import write_json


def fit(args):
    run, evidence, output = args
    polish(run, evidence, output)


def sensitivity(run, evidence, output):
    output.mkdir(parents=True, exist_ok=False)
    history = json.loads((run / "history.json").read_text())
    inventory = json.loads((evidence / "inventory.json").read_text())
    rates = {r["session_id"]: r.get("sample_rate_hz") for r in inventory["scans"]}
    end = inventory["until_ns"]
    start = end - 48 * 3600 * 10**9
    subsets = {
        f"rate-{rate // 1000000}": [h for h in history if rates[h["session_id"]] == rate]
        for rate in [10000000, 15000000, 20000000]
    }
    subsets.update(
        {
            f"block-{k * 12}-{(k + 1) * 12}h": [
                h
                for h in history
                if start + k * 12 * 3600 * 10**9
                <= h["reference_utc_ns"]
                < start + (k + 1) * 12 * 3600 * 10**9
            ]
            for k in range(4)
        }
    )
    tasks = []
    for name, rows in subsets.items():
        target = output / name
        target.mkdir()
        shutil.copy(run / "result.json", target / "result.json")
        write_json(target / "history.json", rows)
        for row in rows:
            file = row["session_id"] + ".npz"
            (target / file).symlink_to((run / file).resolve())
        tasks.append((target, evidence, output / (name + ".json")))
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(fit, tasks))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "evidence", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    sensitivity(a.run, a.evidence, a.output)
