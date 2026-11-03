"""Measure local element/phase degeneracy on the fixed curved observations."""

import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from fit_s01_69333_tle_parameter import BOUNDS, OUTPUT, SOURCE, exact_frequency, perturb
from inventory_clipped_phase_cohort import load_study
from sgp4.api import Satrec


def run():
    source = json.loads((SOURCE / "bracketing_tles.json").read_text())
    results = json.loads((OUTPUT / "results.json").read_text())
    base = Satrec.twoline2rv(*source["past"]["69333"]["lines"])
    study, *_ = load_study("DSX01-S01", True)
    fitted = results["fitted_c/all_curves/phase_only"]
    keys = {r["component"] for r in fitted["rows"]}
    tracks = [t for t in study.tracks if t["key"] in keys]
    assert len(tracks) == 9 and all(t["key"] in study.curved_keys for t in tracks)
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    phase = fitted["phase_s"]

    def f(sat, shift):
        return exact_frequency(sat, source["anchor_utc_ns"], times, shift)[0]

    def centered(values):
        out = []
        for t in tracks:
            y = t["rf_hz"] / 11.5e9 * values[np.searchsorted(times, t["times"])]
            out.append(y - y.mean())
        return np.concatenate(out)

    phase_tangent = centered((f(base, phase + 0.01) - f(base, phase - 0.01)) / 0.02)

    def project(vector):
        return vector - phase_tangent * (vector @ phase_tangent) / (phase_tangent @ phase_tangent)

    vectors, retained = {}, {}
    for model, bound in BOUNDS.items():
        epsilon = bound / 100
        derivative = centered((f(perturb(base, model, epsilon), phase)
                               - f(perturb(base, model, -epsilon), phase)) / (2 * epsilon))
        projected = project(derivative)
        retained[model] = float(np.linalg.norm(projected) / np.linalg.norm(derivative))
        vectors[model] = projected / np.linalg.norm(projected)
    rate = project(centered(times - 65))
    rate /= np.linalg.norm(rate)
    names = list(vectors)
    matrix = np.array([[float(vectors[a] @ vectors[b]) for b in names] for a in names])
    summary = []
    for model in ["phase_only", *BOUNDS]:
        row = results[f"fitted_c/all_curves/{model}"]
        transfer = results[f"fitted_c/omit_target/{model}"]
        target = next(r for r in row["rows"] if r["component"] == "S01-RX1-CH4-T001")
        predicted = next(r for r in transfer["rows"] if r["component"] == target["component"])
        summary.append(dict(model=model, delta=row["delta"], phase_s=row["phase_s"],
                            bic_improvement=fitted["bic"] - row["bic"],
                            target_fit_rms_hz=target["rms_hz"], target_pass=target["passing"],
                            target_transfer_rms_hz=predicted["rms_hz"],
                            target_transfer_pass=predicted["passing"], at_bound=row["at_bound"]))
    matched = True
    for key, value in results.items():
        if key.startswith("c0/"):
            other = results[key.replace("c0/", "fitted_c/", 1)]
            assert abs(value["bic"] - other["bic"]) < 1e-6
            assert value["delta"] == other["delta"]
        assert value["interpolation_error_max_hz"] < 1
        assert value["fit_points"] == (254 if "/all_curves/" in key else 209)
    write(OUTPUT / "identifiability.json", dict(
        names=names, pairwise_cosine_after_track_constants_and_phase_removed=matrix,
        fraction_of_element_tangent_remaining_after_phase_removed=retained,
        cosine_with_empirical_rate_after_phase_removed={k: float(v @ rate)
                                                       for k, v in vectors.items()},
        interpretation="local functional degeneracy, not a parameter covariance or proof of cause",
        summary=summary, c0_fitted_c_matched=matched,
    ))
    files = list(OUTPUT.glob("*.json"))
    write(OUTPUT / "validation.json", dict(
        checks_passed=True, direct_sgp4_final_residuals=True,
        interpolation_error_below_1hz=True, paired_c_arms_match=True,
        curves=9, points=254, linear_calibration_used=False,
        file_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in files if p.name != "validation.json"},
        source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            Path(__file__), Path(__file__).with_name("fit_s01_69333_tle_parameter.py")]},
    ))
    print(json.dumps(dict(summary=summary, rate_cosines={k: float(v @ rate)
                                                       for k, v in vectors.items()})), flush=True)


if __name__ == "__main__":
    run()
