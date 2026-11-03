"""Test every distinct same-scan cold regional-atlas identity, without GPS."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_radial_restarts import assignment_changes
from investigate_dsx01_localization_failures import OUTPUT, context, refreshed
from run_dsx01_clean_region import OUTPUT as CLEAN
from run_dsx01_clean_region import zero_state
from run_dsx01_joint_descent import ARMS, CASES, signature


def unique_atlas(case):
    path = CLEAN / case / "atlas.json"
    data = json.loads(path.read_text())
    result, seen = [], set()
    for index, node in enumerate(data["nodes"]):
        key = signature(node)
        if key not in seen:
            result.append(dict(node=node, source_index=index))
            seen.add(key)
    return result


def worker(case, node_id):
    directory = OUTPUT / case / "regional_candidates"
    directory.mkdir(exist_ok=True)
    path = directory / f"node_{node_id:02d}.json"
    if path.exists():
        return
    protocol_path = CLEAN / case / "protocol.json"
    protocol_blob = protocol_path.read_bytes()
    protocol = json.loads(protocol_blob)
    scan, sigma, original, _, bindings, _ = context(case)
    if (protocol["zero_initial_radio_and_phase"] is not True
            or protocol["inherited_seed_files_read"] is not False
            or protocol["GPS_or_following_TLE_in_inference"] is not False
            or protocol["satellite_whitelist"] is not None
            or protocol["candidate_count"] != len(scan.norads)
            or protocol["box_width_km"] != 25
            or not np.isclose(protocol["sigma_hz"], sigma)):
        raise ValueError("regional RF atlas does not meet causal cold-start protocol")
    item = unique_atlas(case)[node_id]
    node = dict(seed=dict(rows=item["node"]["seed"]["rows"], state=zero_state(scan)),
                aliases=item["node"]["aliases"])
    arms = {}
    for arm in ARMS:
        p, result, history = refreshed(scan, sigma, node, arm)
        arms[arm] = dict(fit=result, phase_rounds=history, reference=p.reference,
                         state=p.state(result["parameters"]))
    atlas_path = CLEAN / case / "atlas.json"
    bindings[str(atlas_path)] = hashlib.sha256(atlas_path.read_bytes()).hexdigest()
    bindings[str(protocol_path)] = hashlib.sha256(protocol_blob).hexdigest()
    write(path, dict(case=case, node_id=node_id, source_index=item["source_index"], arms=arms,
                     node=node, changes=assignment_changes(original, node), GPS_used=False,
                     inherited_nuisance_state_and_position_discarded=True,
                     common_center_start=(0., 0.), source_bindings=bindings, status="complete"))


def run(workers):
    jobs = [(case, i) for case in CASES for i in range(len(unique_atlas(case)))]

    def one(case, index):
        log = OUTPUT / f"{case}_regional_{index:02d}.log"
        with log.open("w") as handle:
            p = subprocess.run([sys.executable, __file__, "--case", case, "--node-id", str(index)],
                               stdout=handle, stderr=subprocess.STDOUT, check=False,
                               env=dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                                        PYTHONPATH="src:tools"))
        return dict(case=case, node_id=index, returncode=p.returncode)

    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, c, i) for c, i in jobs]
        for future in as_completed(futures):
            row = future.result()
            print(json.dumps(row), flush=True)
            if row["returncode"]:
                failures.append(row)
    if failures:
        raise RuntimeError(failures)
    for case in CASES:
        directory = OUTPUT / case / "regional_candidates"
        choices = [json.loads((directory / f"node_{i:02d}.json").read_text())
                   for i in range(len(unique_atlas(case)))]
        selected = min(choices, key=lambda r: r["arms"]["c0"]["fit"]["score"])
        write(OUTPUT / case / "regional_candidates.json", dict(
            case=case, choices=choices, selected_id=selected["node_id"],
            selection="full c0 score after phase refresh; no GPS", GPS_used=False,
            grid_scope="25 RF discovery nodes over the full 25x25 km box",
            status="complete"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--node-id", type=int)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    if args.case:
        worker(args.case, args.node_id)
    else:
        run(args.workers)
