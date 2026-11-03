"""Use remaining independently matched curved fragments as position evidence.

All ALGO02 curved calibration and offered linear observations stay fixed. Extra
curved fragments only enter the same conditional predictive distribution as
linear extensions; they cannot recalibrate receiver or satellite corrections.
"""

import argparse
import time
from pathlib import Path
import numpy as np
from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as INCUMBENT, refit
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT = ROOT / "reports/2026_10_19_algo03_conditional_curved_extensions"


def disjoint_additions(rows, tracks, curved, occupied):
    """Conservative whole-track exclusivity; no data-dependent tail trimming."""
    by_key = {track["key"]: i for i, track in enumerate(tracks)}
    seen = set(occupied)
    chosen = []
    for row in rows:
        i = by_key[row["component"]]
        ids = tracks[i]["observation_ids"]
        if (row["association_source"] != "frozen_calibration_extension" or i not in curved or
                len(ids) < 6 or len(ids) != len(set(ids)) or seen.intersection(ids)):
            continue
        chosen.append((row, i))
        seen.update(ids)
    return chosen


def additions(p, x, metrics, original_entries):
    extra = extend_associations(p, x, metrics)
    occupied = {oid for row in metrics["tracks"] for oid in row["observation_ids"]}
    occupied.update(oid for entry in original_entries for oid in entry["observation_ids"])
    entries = []
    for row, i in disjoint_additions(extra["tracks"], p.scan.tracks, set(p.scan.curved), occupied):
        track = p.scan.tracks[i]
        entry = dict(track_index=i, component=track["key"], candidate_index=row["candidate_index"],
            norad=row["norad"], alias=0, points=len(track["times"]),
            observation_ids=track["observation_ids"], source_active_curvature=True)
        view, values, _, _, _ = linear_geometry(p, [entry])
        geometry = geometry_features(view, x, 0.)
        prediction = view.q*geometry["intercept"]+geometry["features"]@p.calculate(x)["coefficient"]
        entry["alias"] = int(np.rint(-np.mean(values-prediction)/PERIOD))
        entries.append(entry)
    return entries


def run(case):
    OUT.mkdir(exist_ok=True)
    output = OUT / (case + ".json")
    if output.exists():
        raise FileExistsError("preserve scientific evidence")
    began = time.monotonic()
    scan, node, keep, powers, means, model, _, baseline = context(case, "archived")
    source = read(INCUMBENT / (case + ".json"))
    original_entries = source["results"]["all_linear"]["entries"]
    original = source["results"]["all_linear"]["policy_arms"]
    saved = baseline["c0"]
    p = make_problem(scan, node, keep, "c0", np.array(saved["phase_reference"]),
                     powers, means, model["multiplier"], model["nu"])
    x = np.array(saved["endpoint_east_north_km"])
    added = additions(p, x, retained_metrics(p, x), original_entries)
    entries = original_entries+added
    pair = ({arm: refit(scan, node, keep, powers, means, model, arm, entries)
             for arm in ("c0", "fitted_c")} if added else original)
    valid = pair_passes(pair, include_linear=True) if added else True
    write(output, dict(case=case, arms=pair, paired_valid=valid,
        policy_arms=pair if valid else original, incumbent_arms=original,
        original_linear_entries=original_entries, additional_curved_entries=added,
        added_tracks=len(added), added_points=sum(entry["points"] for entry in added),
        original_curved_mask=keep, powers=powers, GPS_used=False,
        original_curved_calibration_and_offered_linear_data_preserved=True,
        no_additional_calibration_feedback_or_owner_votes=True, both_c_arms_same_additions_and_budget=True,
        full_shared_predictive_covariance_preserved=True, no_original_points_removed=True,
        source_sha256=sha(Path(__file__)), incumbent_sha256=sha(INCUMBENT / (case + ".json")),
        seconds=time.monotonic()-began))
    print(case, "conditional curved", len(added), "tracks", sum(e["points"] for e in added),
          "points", "paired", valid, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    run(parser.parse_args().case)
