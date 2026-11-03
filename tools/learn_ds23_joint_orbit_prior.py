"""Qualify phase/shape correlations using chronological pre-scan TLE history."""

import argparse
from pathlib import Path
import numpy as np
from ds23_joint_orbit_prior import transition, qualify
from run_algo01_ds23_sample import ROOT, read, write, sha
from probe_ds23_history_calibrated_phase import HISTORY

OUT = ROOT / "reports/2026_10_19_algo03_joint_orbit_prior"


def run(case):
    OUT.mkdir(exist_ok=True)
    output = OUT / (case + "_prior.json")
    if output.exists():
        raise FileExistsError("preserve causal qualification evidence")
    history = read(HISTORY / (case + ".json"))
    forecast = read(HISTORY / (case + "_forecast.json"))
    assert forecast["history_sha256"] == sha(HISTORY / (case + ".json"))
    assert forecast["strictly_pre_RF"] and not forecast["GPS_or_radio_used"]
    cutoff = history["cutoff_utc_ns"]
    rows = []
    rejected = {}
    for number, versions in history["past_versions"].items():
        assert all(v["epoch"] <= cutoff and v["collected_utc_ns"] <= cutoff for v in versions)
        for index in range(2, len(versions)):
            trio = versions[index-2:index+1]
            try:
                result = transition(*trio)
                reason = "noncausal_or_unordered" if result is None else None
                if result and result["target_utc_ns"] > cutoff:
                    reason = "target_not_pre_RF"
                if result and not np.isfinite(np.r_[result["shape_z"],result["phase_residual_s"],result["predicted_sigma_s"]]).all():
                    reason = "nonfinite_transition"
            except ValueError as error:
                reason = str(error)
            if reason:
                rejected[reason] = rejected.get(reason, 0)+1
            else:
                rows.append(dict(norad=int(number), **result))
    validation, original = forecast["distribution_validation"], forecast["original_distribution_validation"]
    phase_qualified = validation["count"] >= 30 and validation["negative_twice_log_density"] < original["negative_twice_log_density"]
    independent = dict(shrinkage=0., multiplier=1., nu=None)
    prefix = forecast["prefix_distribution"] if phase_qualified else independent
    full = forecast["all_past_distribution"] if phase_qualified else independent
    selected = qualify(rows, forecast["temporal_split_boundary_ns"], prefix, full)
    write(output, dict(case=case, selection=selected, transitions=rows, rejected=rejected,
        prefix_phase_model=prefix, full_phase_model=full,
        columns=["phase_at_midpoint", "reference_aligned_mean_motion", "inclination", "RAAN"],
        history_sha256=sha(HISTORY / (case + ".json")),
        phase_forecast_sha256=sha(HISTORY / (case + "_forecast.json")),
        source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT / "tools/ds23_joint_orbit_prior.py"),
        no_RF_or_GPS_or_postscan_elements_used=True, unchanged_marginal_scales=True,
        cutoff_utc_ns=cutoff, warning="later causal TLE innovations are correlated proxies, not orbit truth"))
    print(case, "joint prior", "qualified", selected["qualified"], "gain", selected.get("validation_gain"),
          "transitions", len(rows), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    run(parser.parse_args().case)
