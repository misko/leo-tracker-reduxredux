#!/usr/bin/env python3
"""Fit the longest scanner tracks and proposed long joins to causal Starlink TLEs."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from evaluate_scan_pnt_cohort import make_arc, orbit_bank, score_arc, write_json

from leo.analysis.research.scan_pnt_experiment import polynomial_comparison


def evaluate(job):
    source, output = map(Path, job)
    doc = json.loads(source.read_text())
    inv = doc["inventory"]
    sid = inv["session_id"]
    dest = output / "orbit-results" / f"{sid}.json"
    if dest.exists():
        return
    start = time.monotonic()
    payload = (source.parent / inv["tle_file"]).read_text()
    selected = [max(doc["episodes"], key=lambda e: e["support_s"][1] - e["support_s"][0])]
    selected += [
        e
        for e in doc["episodes"]
        if e not in selected and e["support_s"][1] - e["support_s"][0] >= 45
    ]
    by_id = {e["episode_id"]: e for e in doc["episodes"]}
    joins = []
    for j in doc["joins"]:
        left, right = by_id[j["left_track_id"]], by_id[j["right_track_id"]]
        support = [
            min(left["support_s"][0], right["support_s"][0]),
            max(left["support_s"][1], right["support_s"][1]),
        ]
        if support[1] - support[0] >= 60:
            joins.append(
                {
                    "episode_id": left["episode_id"] + "+" + right["episode_id"],
                    "members": left["members"] + right["members"],
                    "support_s": support,
                    "label": left["label"] + " → " + right["label"],
                    "join_proposal": j,
                }
            )
    # Include all >=60 s pair hypotheses, including geometrically rejected pairs.
    selected += joins
    results = []
    for ep in selected:
        arc = make_arc(doc, ep["members"])
        results.append({**ep, "polynomial": polynomial_comparison(arc), "controls": []})
    for shift in (0, -600, 600):
        bank = orbit_bank(payload, inv["reference_utc_ns"], wrong_time_s=shift)
        for ep in results:
            arc = make_arc(doc, ep["members"])
            match = score_arc(arc, bank, ep["polynomial"], wide=shift == 0)
            if shift == 0:
                ep["match"] = match
            else:
                match.pop("residual_hz", None)
                ep["controls"].append({"wrong_time_s": shift, **match})
    write_json(dest, {"session_id": sid, "inventory": inv, "episodes": results})
    print(f"{sid}: {len(results)} orbit hypotheses; {time.monotonic() - start:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted((args.output / "evidence").glob("scan*.json"))
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(evaluate, [(str(p), str(args.output)) for p in paths]))


if __name__ == "__main__":
    main()
