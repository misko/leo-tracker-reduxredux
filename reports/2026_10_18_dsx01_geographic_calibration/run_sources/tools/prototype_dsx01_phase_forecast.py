"""Predict nonzero orbital phase-prior means from strictly past TLE innovations."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import causal_history, fit_shrinkage, innovation
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import OUTPUT, geometry_problem
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_dsx01_receiver_phase import PhaseScaleProblem


def phase_prior(case):
    path = OUTPUT / "phase_forecast" / case / "prior.json"
    if path.exists():
        return json.loads(path.read_text())
    data = causal_history(case)
    pairs = []
    latest = []
    sample = np.array([0.0, 150.0, 300.0])
    for n, row in data["candidates"].items():
        history = sorted(row["past_versions"], key=lambda r: r["epoch"])
        for a, b, c in zip(history, history[1:], history[2:], strict=False):
            _, _, ab = innovation(b, a, b["epoch"], sample)
            _, _, bc = innovation(c, b, c["epoch"], sample)
            ratio = (c["epoch"] - b["epoch"]) / (b["epoch"] - a["epoch"])
            pairs.append(
                dict(
                    norad=n,
                    predictor=np.array([-ab * ratio**2]),
                    target=np.array([-bc]),
                    available_utc_ns=max(a["collected_utc_ns"], b["collected_utc_ns"]),
                    target_collection_utc_ns=c["collected_utc_ns"],
                    target_epoch=c["epoch"],
                )
            )
        current = row["latest_causal"]
        old = [r for r in history if r["epoch"] < current["epoch"]]
        if old:
            previous = max(old, key=lambda r: r["epoch"])
            _, _, phase = innovation(current, previous, current["epoch"], sample)
            age = (data["origin_utc_ns"] - current["epoch"]) / (
                current["epoch"] - previous["epoch"]
            )
            latest.append(
                dict(
                    norad=n,
                    previous_phase_error_s=phase,
                    age_to_update_interval_ratio=age,
                    raw_prior_mean_s=-phase * min(max(age, 0), 1) ** 2,
                )
            )
    # Positive coefficient corresponds to persistent unmodeled along-track
    # acceleration. Non-predictive/anti-correlated histories shrink to zero.
    alpha = max(0.0, fit_shrinkage(pairs))
    means = {r["norad"]: float(alpha * r["raw_prior_mean_s"]) for r in latest}
    result = dict(
        case=case,
        cutoff_utc_ns=data["cutoff_utc_ns"],
        coefficient=alpha,
        phase_mean_s=means,
        chronological_own_epoch_proxy_pairs=pairs,
        latest_prediction_metadata=latest,
        no_CFO_receiver_position_GPS_or_future_TLE_read=True,
        own_epoch_states_are_proxy_references_not_orbit_truth=True,
        hypothesis="phase prediction error grows quadratically with propagation age",
        prediction_age_capped_at_one_previous_update_interval=True,
        regression_regularization_scale_seconds=0.3,
        coefficient_bounds=[0, 1],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, result)
    return result


class PhaseMeanProblem(PhaseScaleProblem):
    def __init__(self, problem, means):
        super().__init__(problem, factor=1.0)
        self.prior_mean = np.array(
            [means.get(str(int(problem.scan.norads[j])), 0.0) for j in problem.labels]
        )

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        r[self.phase_slice] -= self.prior_mean / self.scan.sigma[self.labels]
        return (r, diagnostics) if details else r


def forecast_problem(*args, means):
    return PhaseMeanProblem(geometry_problem(*args, mean_sigma=10, height_sigma=0), means)


def run(case, method):
    prior = phase_prior(case)
    directory = OUTPUT / "phase_forecast" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    scan = Scan(case)
    source = SOURCE / case / f"{method}_center.json"
    seed = json.loads(source.read_text())

    def factory(*args):
        return forecast_problem(*args, means=prior["phase_mean_s"])

    fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
    write(path, fits)
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            constant_phase_prior_mean_only_changes=True,
            original_phase_variances_bounds_candidate_labels_aliases_and_radio_priors_retained=True,
            c0_fitted_c_use_same_forecast_means_nominations_geographic_starts_and_24_iteration_budget=True,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            prior_sha256=hashlib.sha256((directory.parent / "prior.json").read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    print(
        case,
        method,
        "alpha",
        prior["coefficient"],
        {a: f["east_north_km"] for a, f in fits.items()},
        flush=True,
    )
    return fits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, default="receiver_smooth")
    a = p.parse_args()
    run(a.case, a.method)
