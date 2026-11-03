"""Matched blind tests of causal orbital prior means, independent of radio/GPS."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as engine
from associate_merged_track_catalogue import write
from dsx01_causal_forecast import INPUT, VARIANTS, CausalForecast

OUTPUT = engine.ROOT / "reports/2026_10_18_dsx01_causal_forecast"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    directory = OUTPUT / args.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_radio_or_future_TLE_in_prior_means=True,
            latest_causal_TLE_plus_past_only_state_innovation_trend=True,
            mean_formula="-shrinkage*clip(age/epoch_gap,0,2)*previous_minus_latest_standardized_state",
            maximum_absolute_standardized_mean=3,
            phase_or_full4_prior_mean_controls=True,
            trend_shrinkage=1,
            history_shrinkage_candidates=[0, 0.25, 0.5, 0.75, 1],
            history_selection="Earlier causal prefix transition robust phase-proxy loss; no radio",
            epoch_gap_s_must_be_positive_otherwise_zero_mean=True,
            original_prior_variances_and_original_curved_observations_preserved=True,
            matched_c0_fitted_c_labels_aliases_point_noise_grid_and_budgets=True,
            no_linear_track_calibration=True,
            causal_forecast_input_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),
            source_sha256={
                str(p.relative_to(engine.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    Path(__file__),
                    engine.ROOT / "tools/dsx01_causal_forecast.py",
                    engine.ROOT / "tools/dsx01_causal_correlation.py",
                ]
            },
        ),
    )
    engine.OUTPUT, engine.JointMarginal = OUTPUT, CausalForecast
    engine.run(args.case, variants=args.variants)
