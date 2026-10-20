"""Path-explicit, GPS-free ALGO02 inference for one prepared DS23 recording.

Discovery runs in a separate process because its inference read guard is
process-global. Other stages only bind legacy paths inside this worker process;
there are no cross-recording globals shared by concurrently executing workers.
The original conservative ALGO01 result remains ``result.json``. ALGO02 writes
``algo02_result.json`` and never reads a development-cohort result directory.
"""

import argparse
import copy
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from run_algo01_ds23_sample import ROOT, read, sha, write

ARMS = ("c0", "fitted_c")
ALGORITHM = "ALGO02-v1"
CENTER = (37.906, -122.545)


def bind_run_directory(run_dir):
    """The caller must give each recording an isolated Python process."""
    import run_algo01_ds23_sample as initial
    import evaluate_ds23_phase_refreshed as discovery

    initial.OUT = Path(run_dir).resolve()
    discovery.OUTPUT = initial.OUT
    return initial


def load_scan(run_dir, case):
    from evaluate_ds23_phase_refreshed import FreshScan

    root = Path(run_dir)
    scan = FreshScan(root / case, noise_mode="radio")
    prior = root / "causal_prior" / case
    scan.previous_tle_path = prior / "previous.tle"
    scan.receipt = read(prior / "receipt.json")
    if sha(scan.previous_tle_path) != scan.receipt["previous_tle_sha256"]:
        raise ValueError("causal previous elements changed")
    validate_prior_receipt(scan.receipt, read(prior / "previous_receipt.json"),
                           sha(scan.previous_tle_path))
    return scan


def validate_prior_receipt(receipt, previous, digest):
    cutoff = receipt["cutoff_utc_ns"]
    if cutoff > receipt["origin_utc_ns"] or receipt["reference_position_used"] is not False:
        raise ValueError("invalid causal bank cutoff or geographic reference use")
    if tuple(receipt["search_center"]) != CENTER or receipt["search_box_width_km"] != 25.:
        raise ValueError("initial regional search differs from the frozen 25km box")
    if previous["catalogue_sha256"] != digest:
        raise ValueError("previous element provenance digest changed")
    for record in previous["sources"].values():
        if record["epoch_utc_ns"] > cutoff or record["collected_utc_ns"] > cutoff:
            raise ValueError("post-scan previous element provenance")


def validate_history(raw, forecast, scan, raw_sha256):
    """Check every historical candidate, including candidates not RF selected."""
    if not forecast.get("strictly_pre_RF") or forecast.get("GPS_or_radio_used") is not False:
        raise ValueError("phase prior is not certified pre-RF")
    if raw["case"] != scan.case or forecast["case"] != scan.case:
        raise ValueError("causal history belongs to another recording")
    if forecast["history_sha256"] != raw_sha256:
        raise ValueError("causal history digest changed")
    if any(raw[name] != scan.receipt[name] for name in ("origin_utc_ns", "cutoff_utc_ns")):
        raise ValueError("causal history timing belongs to another scan")
    cutoff = raw["cutoff_utc_ns"]
    for versions in raw["past_versions"].values():
        for version in versions:
            if version["epoch"] > cutoff or version["collected_utc_ns"] > cutoff:
                raise ValueError("post-scan element in causal history")
    valid = forecast["distribution_validation"]
    original = forecast["original_distribution_validation"]
    qualified = (valid["count"] >= 30 and
                 valid["negative_twice_log_density"] < original["negative_twice_log_density"])
    model = (copy.deepcopy(forecast["all_past_distribution"]) if qualified else
             dict(shrinkage=0., multiplier=1., nu=None, fallback=True))
    if not 0 <= model["shrinkage"] <= 1 or not np.isfinite(model["multiplier"]) or model["multiplier"] <= 0:
        raise ValueError("invalid historical phase distribution")
    return model, bool(qualified)


def pair_passes(pair, include_linear=False):
    """The same observations/hypothesis must qualify in both c arms."""
    for arm in ARMS:
        record = pair[arm]
        tracks = record["gates"]["tracks"] + (record.get("linear_gates", []) if include_linear else [])
        if not tracks or not all(t["compatible"] for t in tracks):
            return False
        if include_linear and record["final_phase_change_s"] > .01:
            return False
        x = np.asarray(record["endpoint_east_north_km"])
        if x.shape != (2,) or not np.isfinite(x).all() or np.any(abs(x) > 12.5 + 1e-8):
            return False
    return True


def paired_policy(curved, linear):
    """Never choose one c arm using the other arm's data or evaluation error."""
    accepted = pair_passes(linear, include_linear=True)
    return (linear if accepted else curved), accepted


def history_fit(scan, node, original_keep, powers, means, model):
    from investigate_algo01_ds23_0217 import problem
    from probe_ds23_history_calibrated_phase import refit

    base = problem(scan, node, "c0", original_keep)
    keep = np.array(original_keep, bool, copy=True)
    steps = []
    pair = None
    for epoch in range(4):
        if not keep.any():
            break
        pair = {arm: refit(scan, node, keep, arm, powers, means, model["multiplier"], model["nu"])
                for arm in ARMS}
        failed = {r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"]
                  if not r["compatible"]}
        steps.append(dict(epoch=epoch, input_points=int(keep.sum()), failed=sorted(failed)))
        if not failed or epoch == 3:
            break
        for row, sl in zip(base.rows, base.slices, strict=True):
            if row["component"] in failed:
                keep[sl] = False
    return pair, keep, steps


def infer_algo02(run_dir, case):
    from audit_ds23_algo01_coverage import retained_metrics
    from evaluate_ds23_family_weighting import confidence_for, family_weights
    from investigate_algo01_ds23_0217 import problem
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_predictive_linear import refit as linear_refit, select_entries

    run_dir = Path(run_dir).resolve()
    directory = run_dir / case
    output = directory / "algo02_result.json"
    if output.exists():
        return read(output)
    started = time.monotonic()
    original = read(directory / "result.json")
    common = dict(case=case, algorithm=ALGORITHM, GPS_used=False, future_TLE_used=False,
                  region_center=CENTER, box_width_km=25., start_east_north_km=[0., 0.],
                  paired_c_masks_aliases_identities_and_budgets=True,
                  baseline_sha256=sha(directory / "result.json"),
                  engine_sha256=sha(Path(__file__)))
    if original["status"] != "complete":
        result = dict(common, status="failed", reason="initial_" + original["status"], policy_arms={})
        write(output, result)
        return result
    scan = load_scan(run_dir, case)
    node = original["final_node"]
    original_keep = np.asarray(original["final_mask"], bool)
    p = problem(scan, node, "c0", original_keep)
    confidence = confidence_for(scan, node, original_keep, original)
    powers, owners, counts = family_weights(p.rows, p.members, scan.tracks, confidence,
        "cross_rx_support", [int(original_keep[sl].sum()) for sl in p.slices])
    history_root = run_dir / "causal_phase_history"
    raw_path = history_root / (case + ".json")
    forecast_path = history_root / (case + "_forecast.json")
    model, qualified = validate_history(read(raw_path), read(forecast_path), scan, sha(raw_path))
    _, receipts = phase_widths(scan, p.labels)
    means = forecast_phase_mean(receipts, model["shrinkage"])
    curved, keep, history = history_fit(scan, node, original_keep, powers, means, model)
    common.update(weights=powers, confidence=confidence, original_mask=original_keep,
                  mask=keep, curved_gate_history=history,
                  hyperparameters_from_pre_RF_TLE_only=model,
                  earlier_TLE_validation_qualified=qualified,
                  history_sha256=sha(raw_path), history_forecast_sha256=sha(forecast_path),
                  family_owners={str(int(scan.norads[j])): sorted(v) for j, v in owners.items()},
                  family_points={str(int(scan.norads[j])): int(v) for j, v in counts.items()})
    if curved is None or not keep.any() or not pair_passes(curved):
        result = dict(common, status="failed", reason="no_qualified_curved_pair",
                      curved_arms=curved, policy_arms={}, seconds=time.monotonic()-started)
        write(output, result)
        return result
    saved = curved["c0"]
    p = make_problem(scan, node, keep, "c0", np.asarray(saved["phase_reference"]),
                     powers, means, model["multiplier"], model["nu"])
    x = np.asarray(saved["endpoint_east_north_km"])
    entries = select_entries(p, x, retained_metrics(p, x))
    linear = {arm: linear_refit(scan, node, keep, powers, means, model, arm, entries) for arm in ARMS}
    policy, accepted = paired_policy(curved, linear)
    result = dict(common, status="accepted", policy_arms=policy, curved_arms=curved,
                  linear_arms=linear, linear_entries=entries, linear_paired_valid=accepted,
                  fallback=None if accepted else "curved_pair",
                  linear_offered_tracks=len(entries),
                  linear_offered_points=sum(e["points"] for e in entries),
                  linear_used_points=sum(e["points"] for e in entries) if accepted else 0,
                  no_IQ_reread=True, curved_only_calibration_no_linear_normal_equation_update=True,
                  shared_full_calibration_covariance_preserved=True,
                  per_new_curve_constant_sigma_hz=300., unseen_noise_inverse_precision_mean=2.,
                  phase_rounds=5, steps_per_round=48, maximum_curved_gate_rounds=4,
                  no_stationary_history_position_pooling=True, seconds=time.monotonic()-started)
    write(output, result)
    print(case, "ALGO02 accepted", "linear" if accepted else "curved fallback", flush=True)
    return result


def run(run_dir, case, stage):
    run_dir = Path(run_dir).resolve()
    initial = bind_run_directory(run_dir)
    if stage == "discover":
        import evaluate_ds23_phase_refreshed as discovery
        discovery.fit_case(case, noise_mode="radio")
    elif stage == "initial":
        initial.infer(case)
    elif stage == "algo02":
        infer_algo02(run_dir, case)
    else:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--run-dir", str(run_dir),
                        "--case", case, "--stage", "discover"], check=True)
        initial.infer(case)
        infer_algo02(run_dir, case)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--stage", choices=("discover", "initial", "algo02", "all"), default="all")
    args = parser.parse_args()
    run(args.run_dir, args.case, args.stage)
