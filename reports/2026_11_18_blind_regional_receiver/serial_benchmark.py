"""Verify frozen decisions and measure time, using one worker at a time."""

import argparse
import json
from pathlib import Path

import run_study as study


def run(panel, replay_all=False):
    public = study.ROOT / f"public_{panel}"
    path = study.PREDS / (panel + ".json")
    lock = study.read(study.LOCKS / "prediction-lock.json")
    if study.sha(path.read_bytes()) != lock["sha256"][path.name]:
        raise ValueError("prediction digest mismatch")
    rows = {row["id"]: row for row in study.read(path)["cases"]}
    ordered = sorted(rows, key=lambda q: study.sha(("serial-timing-v1/" + q).encode()))
    selected = ordered if replay_all else ordered[:3]
    sample = []
    for qid in selected:
        result = study.dispatch(study.one_query(public, qid), "primary")
        keys = ("status", "reason", "region_id", "latlon", "best_region", "best_latlon")
        if any(result[k] != rows[qid][k] for k in keys):
            raise ValueError("decision changed on serial replay")
        sample.append({k: result[k] for k in
                       ("id", "wall_s", "process_wall_s", "process_cpu_s", "peak_rss_kib")})
    return sample


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panels", nargs="+", choices=study.PANELS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="replay every query in these panels")
    args = parser.parse_args()
    study.freeze()
    data = {panel: run(panel, args.all) for panel in args.panels}
    args.output.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
