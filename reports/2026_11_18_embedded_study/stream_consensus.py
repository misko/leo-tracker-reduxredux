"""Test the proposed combination of online tracking and satellite-family consensus."""

import json
import sys
import time

import numpy as np

import cold_replay as cold
from alternative_replay import consensus

sys.path.insert(0,str(cold.ROOT/"stream"))
from winner_to_fix import track_document, winners as extract


def main():
    recorded = cold.read(cold.ROOT/"stream/winner-positions-all.json")["rows"]
    ref = {r["case"]:r["arms"] for r in recorded if "arms" in r}
    rows = []
    for case in sorted(r["case"] for r in recorded):
        if case not in ref:
            rows.append(dict(case=case,status="missing"))
            continue
        start_time = time.perf_counter()
        doc = cold.read(cold.INPUT/case/"native.json")
        points,meta,half = extract(doc)
        points = [r for r in points if r[4]+half <= meta["duration_s"]+1e-8]
        tracks,_ = track_document(points)
        bank,_ = cold.build_bank(case,meta,check_approximation=False)
        d = cold.descriptors(tracks,bank)
        if d is None:
            rows.append(dict(case=case,status="insufficient"))
            continue
        bias = cold.bias_vote(d)
        vote = cold.grid_vote(d,bias)
        before_consensus = time.perf_counter()
        arms = consensus(d,bias,vote)
        finish = time.perf_counter()
        # Validate before/after input parity with the complete streaming control.
        _,xy,winners,cost = vote
        selected = np.flatnonzero(cost<12.)
        for arm in ("c0","fitted_c"):
            control = cold.solve(d,selected,winners,bias,xy,fitted_c=(arm=="fitted_c"))
            assert control["status"] == ref[case][arm]["status"] == "estimate"
            assert np.allclose(control["xy"],ref[case][arm]["xy"],rtol=0,atol=1e-7)
        rows.append(dict(case=case,status="processed",arms=arms,winners=len(points),
                         both_arms_wall_s=finish-start_time,consensus_wall_s=finish-before_consensus))
    (cold.ROOT/"stream-consensus.json").write_text(json.dumps(rows,allow_nan=False))


if __name__=="__main__":
    main()
