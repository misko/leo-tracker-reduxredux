"""Past-only trend corrections to a latest-causal orbit prior mean.

The latest TLE remains the nominal propagator. A declared extrapolation of the
previous/latest state innovation changes the nuisance prior mean. This is a
sensitivity model, not a validated orbit determination method.
"""

import json

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from dsx01_causal_correlation import CausalCorrelation
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from probe_dsx01_scan_influence import OUTPUT as HISTORY
from sgp4.api import Satrec

from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

VARIANTS = ("phase_trend", "full_trend", "phase_history", "full_history")
INPUT = HISTORY / "causal_forecast_inputs_strict.json"


def trend_mean(direction, age_s, gap_s, shrinkage, *, phase_only=False):
    z = np.asarray(direction, float)
    if (
        z.ndim != 1
        or not len(z)
        or not np.isfinite(z).all()
        or not np.isfinite([age_s, gap_s, shrinkage]).all()
        or gap_s <= 0
        or not 0 <= shrinkage <= 1
    ):
        raise ValueError("finite direction/age, positive epoch gap and shrinkage in [0,1] required")
    value = -shrinkage * np.clip(age_s / gap_s, 0, 2) * z
    if phase_only:
        value[1:] = 0
    value *= min(1.0, 3.0 / max(3.0, float(np.max(abs(value)))))
    return value


def select_history_shrinkage(history, origin_ns):
    """Forecast third causal TLE from the first two; never see future or radio."""
    rows = []
    for number, versions in history.items():
        known = sorted(
            [v for v in versions if v["collected_utc_ns"] <= origin_ns], key=lambda r: r["epoch"]
        )
        unique = {v["epoch"]: v for v in known}
        if len(unique) < 3:
            continue
        a, b, c = list(unique.values())[-3:]
        if not a["collected_utc_ns"] <= b["collected_utc_ns"] <= c["collected_utc_ns"]:
            continue
        # All three orbits are compared at the third publication time, which
        # is a past event known before this radio observation.
        target_ns = c["collected_utc_ns"]
        satellites = tuple(Satrec.twoline2rv(*v["lines"]) for v in [a, b, c])
        catalogue = ElementSetCatalogue((number,) * 3, (int(number),) * 3, satellites)
        p, v, good = ecef_states(catalogue, target_ns, np.array([0.0, 1.0, 2.0]))
        if not good.all():
            continue
        inertial = v[1, 0].copy()
        omega = 7.29211514670698e-5
        inertial[0] -= omega * p[1, 0, 1]
        inertial[1] += omega * p[1, 0, 0]
        denominator = inertial @ inertial
        previous_phase = float((p[0, 0] - p[1, 0]) @ inertial / denominator)
        target_phase = float((p[2, 0] - p[1, 0]) @ inertial / denominator)
        ratio = float(np.clip((target_ns - b["epoch"]) / (b["epoch"] - a["epoch"]), 0, 2))
        forecast = -ratio * previous_phase
        scale = max(1.0, abs(previous_phase))
        rows.append(
            dict(
                norad=int(number),
                old_middle_phase_s=previous_phase,
                observed_next_innovation_s=target_phase,
                unit_trend_prediction_s=forecast,
                scale_s=scale,
                validation_time_ns=target_ns,
            )
        )
    candidates = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    loss = []
    for shrinkage in candidates:
        loss.append(
            float(
                sum(
                    np.log1p(
                        (
                            (
                                r["observed_next_innovation_s"]
                                - shrinkage * r["unit_trend_prediction_s"]
                            )
                            / r["scale_s"]
                        )
                        ** 2
                    )
                    for r in rows
                )
            )
        )
    # Prefer no correction on a tie or if no prefix transitions are available.
    chosen = float(candidates[int(np.argmin(loss))]) if rows else 0.0
    return dict(
        shrinkage=chosen,
        candidates=candidates,
        robust_phase_proxy_loss=loss,
        transitions=rows,
        causal_past_only=True,
    )


class CausalForecast(CausalCorrelation):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown causal trend mean")
        self.forecast_variant = variant
        super().__init__(scan, seed, fitted_c, variant="diag_4", **kwargs)
        history = (
            scan.strict_causal_history
            if hasattr(scan, "strict_causal_history")
            else json.loads(
                (
                    HISTORY.parent
                    / "2026_10_18_dsx01_clean_region"
                    / scan.case
                    / "causal_history.json"
                ).read_text()
            )
        )
        if history["origin_utc_ns"] != scan.receipt["origin_utc_ns"]:
            raise ValueError("causal history observation clock differs")
        from dsx01_inference_audit import validate_history

        validate_history(history["past_versions"], scan.receipt["cutoff_utc_ns"])
        if not hasattr(scan, "causal_forecast_selection"):
            scan.causal_forecast_selection = select_history_shrinkage(
                history["past_versions"], history["origin_utc_ns"]
            )
        self.history_selection = scan.causal_forecast_selection
        self.shrinkage = self.history_selection["shrinkage"] if variant.endswith("history") else 1.0
        old = parse_element_sets(
            (HISTORY / "causal_inputs" / scan.case / "previous.tle").read_text()
        )
        previous = dict(zip(old.satellite_numbers, old.satellites, strict=True))
        self.prior_mean = np.zeros(self.transform.shape[0])
        self.forecast_metadata = {}
        for j, row in self.correlation_metadata.items():
            number = int(scan.norads[j])
            if number not in previous:
                continue
            current = Satrec.twoline2rv(*scan.elements[str(number)]["lines"])
            earlier = previous[number]

            def epoch(s):
                return (s.jdsatepoch + s.jdsatepochF - 2440587.5) * 86400

            gap = epoch(current) - epoch(earlier)
            if gap <= 0:
                continue
            age = scan.receipt["origin_utc_ns"] / 1e9 + 150 - epoch(current)
            mean = trend_mean(
                row["standardized_disagreement"],
                age,
                gap,
                self.shrinkage,
                phase_only=variant.startswith("phase"),
            )
            self.prior_mean[row["indices"]] = mean
            self.forecast_metadata[j] = dict(
                norad=number,
                age_s=age,
                epoch_gap_s=gap,
                standardized_prior_mean=mean,
                phase_prior_mean_s=mean[0] * self.phase_sigma[list(self.labels).index(j)],
            )

    def calculate(self, x):
        result = JointMarginal.calculate(self, x)
        features = result["features"]
        raw = self.values - self.q * result["intercept"] - features @ self.prior_mean
        bound = hierarchical_bound(raw, features, self.point_noise, self.noise_groups)
        latent = bound["coefficient"].copy()
        bound["coefficient"] = self.prior_mean + latent
        bound["latent_coefficient"] = latent
        bound["residual"] = np.r_[bound["residual"], np.sqrt(self.diagonal_logvolume)]
        bound["full_objective_offset"] = bound["normalization_constant"] - self.diagonal_logvolume
        result.update(bound, features=features, latent_features=features)
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            causal_forecast_variant=self.forecast_variant,
            prior_mean=self.prior_mean,
            causal_forecast=self.forecast_metadata,
            history_selected_shrinkage=self.shrinkage,
            shrinkage_selected_from_past_TLE_phase_innovations_only=self.forecast_variant.endswith(
                "history"
            ),
            past_only_history_selection=self.history_selection,
        )
        return result
