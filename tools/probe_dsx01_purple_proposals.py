"""Explain the proposal gap without changing the active association algorithm."""

import itertools
import json

import numpy as np
from associate_merged_track_catalogue import write
from debug_dsx01_purple_basin import ARMS, FAMILY, OUTPUT, SOURCE, family_swap, labels, problem
from iterate_dsx01_profiled_identity import explore
from map_dsx01_clean_region import loss
from run_dsx01_clean_region import load_scan, reference_state


def run():
    scan, sigma = load_scan("DSX01-S01")
    records = {
        i: json.loads((SOURCE / "normal" / f"start_{i:02d}/result.json").read_text())
        for i in (0, 6, 9)
    }
    swaps, refreshes = [], []
    for i in (6, 9):
        record = records[i]
        point = np.asarray(record["arms"]["c0"]["endpoint_east_north_km"])
        p = problem(scan, sigma, record["final_node"], "c0")
        seed, detail = explore(
            scan, reference_state(p.state(point)), point,
            "receiver_smooth", compact_update=False,
        )
        proposed = {r["component"]: r["candidate_norad"] for r in seed["rows"]}
        refreshes.append(dict(
            start_id=i, point=point,
            red_family_candidate_100320_in_top_coherent_proposals="100320" in detail["hypotheses"],
            family_proposed_labels={k: proposed[k] for k in FAMILY},
            all_candidate_hypotheses=detail,
        ))
        for count in range(4):
            for selected in itertools.combinations(FAMILY, count):
                node = family_swap(record["final_node"], records[0]["final_node"], selected)
                for arm in ARMS:
                    for common_zero in (False, True):
                        p = problem(
                            scan, sigma, node, arm,
                            common_reference=np.zeros(len(scan.norads)) if common_zero else None,
                        )
                        swaps.append(dict(
                            recipient_branch=i, point=point, arm=arm,
                            components_swapped=selected, changed_count=count,
                            common_zero_phase_reference=common_zero, score=loss(p, point),
                            all_observations_preserved=True,
                        ))
        print("probed proposal gap", i, flush=True)
    write(OUTPUT / "family_subset_scores.json", swaps)
    write(OUTPUT / "actual_candidate_refresh.json", refreshes)
    print("family labels", labels(records[0]["final_node"]), flush=True)


if __name__ == "__main__":
    run()
