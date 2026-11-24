"""Join the sealed first-member detector lanes to existing full-packet owners."""

from collections import Counter
import gzip
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
from prefix_transfer_0419 import ARMS, checked, observation_id, prefix_scope
from verified_window_transfer_0163 import PINS, controls


PAIR = HERE / "measurements/first-member-0163-resume-acquisition.json.gz"
PAIR_PIN = "5cf1c7e7c785c84913851515242ddcd434b02ee4de33c1a244e3f53732ee7c8f"


def compare_lane(original, candidate, digest):
    old_ids = {digest(factor) for factor in original["candidates"]}
    new_ids = {digest(factor) for factor in candidate["candidates"]}
    if not old_ids:
        return "added_on_previously_empty_lane" if new_ids else "both_empty", old_ids, new_ids
    if not new_ids:
        return "candidate_empty", old_ids, new_ids
    if old_ids == new_ids:
        return "exact_native_factor_set", old_ids, new_ids
    return "same_lane_different_factor_set", old_ids, new_ids


def join():
    from leo.contracts.digests import canonical_digest

    docs, full, _, _, _, owners, witness = controls()
    pair = json.loads(gzip.decompress(checked(PAIR, PAIR_PIN)))["documents"]
    if not pair["result.json"]["document"]["qualified"]:
        raise ValueError("The original authenticated detector pair did not qualify")
    named, integrated = (pair[f"{name}/detections.json"]["document"] for name in ("named", "integrated"))
    stock_scope, _ = prefix_scope(full, named, integrated, witness)
    original_lanes, installed_lanes, candidate_lanes = (stock_scope[name][0]
        for name in ("archived", "installed_prefix", "mixed_prefix"))
    if original_lanes != installed_lanes:
        raise ValueError("Need all 64 visits of chronological named parity to join original owners")
    counts, rows = Counter(), []
    totals = {arm: dict(full=len(owners["installed"][arm]), prefix=Counter()) for arm in ARMS}
    session = full["source"]["session_id"]
    for key, row in original_lanes.items():
        state, a, b = compare_lane(row, candidate_lanes[key], canonical_digest)
        id_ = observation_id(session, row)
        counts[state] += 1
        identity = dict(visit=key[0], receiver=key[1], channel=row["channel"], rf_hz=row["actual_rf_hz"],
                        valid_start_counter=row["valid_start_counter"], observation_id=id_, state=state,
                        exact_shared_factors=len(a & b), old_factor_ids=sorted(a), candidate_factor_ids=sorted(b), owners={})
        if len(a) == len(b) == 1:
            old, new = row["candidates"][0], candidate_lanes[key]["candidates"][0]
            identity["singleton_lane_delta"] = {
                field: new[field] - old[field] for field in ("fractional_tracking_cfo_hz", "integer_epoch_sample",
                                                            "fractional_epoch_offset_samples", "candidate_rank")
            }
        for arm in ARMS:
            owner = owners["installed"][arm].get(id_)
            if owner is not None:
                identity["owners"][arm] = owner
                totals[arm]["prefix"][state] += 1
                totals[arm]["prefix"]["original_native_assignment_ambiguous"] += len(a) > 1
        if state != "both_empty" or identity["owners"]:
            rows.append(identity)
    return dict(case="DS30-0163", qualified=True, pair_sha256=PAIR_PIN, full_named_pins=PINS,
                bound_full_terminal=docs["installed/candidate/joint-research-receipt.json"]["receipt"]["terminal_sha256"],
                same_original_clocks_and_native_metadata=True, original_named_prefix_exact=True,
                factor_ids="canonical SHA-256 of exact typed factor rows, tested only within one signed lane",
                owner_scope="archived full-recording installed 20 ms position solution, joined offline",
                candidate_scope="unfiltered selected sparse 20/8 first-member terminal, no whole-record receiver or fit",
                admitted_lanes=len(original_lanes), lane_counts=dict(counts), arms=totals, comparable_nonempty_lanes=rows)


if __name__ == "__main__":
    print(json.dumps(join(), sort_keys=True, indent=2, allow_nan=False))
