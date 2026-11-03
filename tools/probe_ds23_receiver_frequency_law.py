"""Matched ALGO03 receiver-law experiment on frozen ALGO02 evidence.

No supplied location enters fitting or model selection. An unchanged-law
replay is a numerical null control; every policy preserves original points.
"""

import argparse
import time
from pathlib import Path
import numpy as np
from ds23_receiver_frequency_law import receiver_frequency_law
from algo02_scan import pair_passes
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import refit as curved_refit
from probe_ds23_predictive_linear import OUT as INCUMBENT, refit as linear_refit
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / "reports/2026_10_19_algo03_receiver_frequency_law"


def run(case, null_control=False):
    began = time.monotonic()
    OUT.mkdir(exist_ok=True)
    output = OUT / (case + ("_null" if null_control else "") + ".json")
    if output.exists():
        raise FileExistsError("preserve completed scientific evidence")
    scan, node, keep, powers, means, model, _, baseline = context(case, "archived")
    source = read(INCUMBENT / (case + ".json"))
    entries = source["results"]["all_linear"]["entries"]
    incumbent = source["results"]["all_linear"]["policy_arms"]
    law = "fractional_RF" if null_control else "additive_Hz"
    changed = receiver_frequency_law(scan, law)
    curved = {arm: curved_refit(changed, node, keep, arm, powers, means,
                               model["multiplier"], model["nu"]) for arm in ("c0", "fitted_c")}
    curved_valid = pair_passes(curved)
    linear = {arm: linear_refit(changed, node, keep, powers, means, model, arm, entries)
              for arm in ("c0", "fitted_c")}
    linear_valid = pair_passes(linear, include_linear=True)
    policy = linear if curved_valid and linear_valid else (curved if curved_valid else incumbent)
    delta = {arm: float(np.linalg.norm(np.asarray(policy[arm]["endpoint_east_north_km"]) -
             incumbent[arm]["endpoint_east_north_km"])) for arm in ("c0", "fitted_c")}
    write(output, dict(case=case, law=law, curved_arms=curved, linear_arms=linear,
        curved_paired_valid=curved_valid, linear_paired_valid=linear_valid, policy_arms=policy,
        policy="linear" if curved_valid and linear_valid else ("curved" if curved_valid else "incumbent"),
        incumbent_arms=incumbent, endpoint_displacement_km=delta, mask=keep, powers=powers,
        entries=entries, no_original_points_removed=True, all_linear_IDs_labels_aliases_frozen=True,
        original_curved_IDs_and_calibration_rules_preserved=True, no_GPS_used=True,
        new_nuisance_coordinates=0, numerical_prior_amplitude_at_11_5GHz_unchanged=True,
        both_c_arms_same_hypothesis_observations_and_5x48_budget=True,
        source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT / "tools/ds23_receiver_frequency_law.py"),
        incumbent_sha256=sha(INCUMBENT / (case + ".json")), seconds=time.monotonic()-began))
    print(case, law, "curved", curved_valid, "linear", linear_valid, "displacement", delta, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--null-control", action="store_true")
    args = parser.parse_args()
    run(args.case, args.null_control)
