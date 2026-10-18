"""Integrate shared satellite-error modes rather than freely fit each correction."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_orbit_modes import build_modes
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import (
    low_rank_marginal,
    paired_frequency_modes,
    project_constant_features,
)
from leo.analysis.research.retained_track_likelihood import PERIOD

VARIANTS = ("student_none", "student_old_new", "student_physical", "mixture_physical")


class MarginalFamilies(AnchoredFamilies):
    def __init__(
        self,
        scan,
        seed,
        method,
        fitted_c,
        anchor,
        *,
        kind="physical",
        likelihood="student",
        scale=1.0,
        provided_modes=None,
        curve_bias_sigma=1000.0,
        satellite_bias_sigma=0.0,
    ):
        self.ready = False
        super().__init__(scan, seed, method, fitted_c, anchor)
        if kind not in ("none", "old_new", "physical") or likelihood not in (
            "gaussian",
            "student",
            "mixture",
        ):
            raise ValueError("unknown covariance/likelihood control")
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("positive finite orbital scale required")
        self.kind, self.likelihood, self.mode_scale = kind, likelihood, scale
        if (
            curve_bias_sigma <= 0
            or satellite_bias_sigma < 0
            or not np.isfinite([curve_bias_sigma, satellite_bias_sigma]).all()
        ):
            raise ValueError("finite positive curve and nonnegative satellite bias scales required")
        self.curve_bias_sigma, self.satellite_bias_sigma = curve_bias_sigma, satellite_bias_sigma
        self.supported = []
        for j in self.labels:
            owners = {
                (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                for i, row in zip(self.members, self.rows, strict=True)
                if row["candidate_index"] == j
            }
            if len(owners) >= 2 and kind != "none":
                self.supported.append(j)
        self.mode_bank, self.mode_metadata = (None, {})
        if kind != "none":
            self.mode_bank, self.mode_metadata = (
                provided_modes
                if provided_modes is not None
                else build_modes(scan, self.labels, self.supported, kind)
            )
            self.mode_bank = {
                k: (v * scale if k != "time_s" else v) for k, v in self.mode_bank.items()
            }
        self.rank = 0 if kind == "none" else len(self.mode_bank["position_km"]) // len(self.labels)
        self.pieces = []
        self.group_pieces = defaultdict(list)
        self.group_points = defaultdict(int)
        for i, row, block in zip(self.members, self.rows, self.slices, strict=True):
            t = scan.tracks[i]
            n = len(t["times"])
            cut = row["split_at"] if method == "penalized_split" else -1
            slices = [slice(0, n)] if cut <= 0 else [slice(0, cut), slice(cut, n)]
            for sl in slices:
                start, stop = block.start + sl.start, block.start + sl.stop
                w, volume = (scan.ou if method == "correlated_noise" else scan.white)[i]
                if cut > 0:
                    w, volume = np.eye(sl.stop - sl.start) / 150, 0.0
                _, projection, bias_volume = project_constant_features(
                    np.zeros(sl.stop - sl.start),
                    np.eye(sl.stop - sl.start),
                    w,
                    bias_sigma=curve_bias_sigma,
                )
                item = dict(
                    track=i,
                    local=sl,
                    flat=slice(start, stop),
                    projection=projection,
                    volume=volume + bias_volume,
                )
                self.group_pieces[row["candidate_index"]].append(len(self.pieces))
                self.pieces.append(item)
            self.group_points[row["candidate_index"]] += n
        self.ready = True

    def calculate(self, x):
        state = super().decode(x)
        f, e = super().predicted(x)
        modes = (
            np.zeros((len(self.flat_times), 0))
            if self.mode_bank is None
            else paired_frequency_modes(
                self.orbit_sky(state),
                self.mode_bank,
                self.flat_times,
                self.flat_labels,
                state["phases"][self.labels],
                *latlon(x[:2]),
            )
        )
        if self.satellite_bias_sigma:
            modes = np.column_stack(
                (modes, np.full(len(self.flat_times), self.satellite_bias_sigma))
            )
        raw = np.empty(len(self.flat_times))
        native_modes = modes.copy()
        for i, block, alias in zip(self.members, self.slices, self.alias, strict=True):
            t = self.scan.tracks[i]
            q = t["rf_hz"] / 11.5e9
            raw[block] = (
                t["values"] + alias * PERIOD - self.scan.hardware(t, state["beta"]) - q * f[block]
            )
            native_modes[block] *= q
            if self.method == "receiver_smooth":
                raw[block] -= q * self.scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        residuals, statistics, coefficients = [], {}, {}
        for j in self.labels:
            pieces = [self.pieces[k] for k in self.group_pieces[j]]
            r = np.concatenate([p["projection"] @ raw[p["flat"]] for p in pieces])
            u = np.vstack([p["projection"] @ native_modes[p["flat"]] for p in pieces])
            result = low_rank_marginal(
                r,
                u,
                self.group_points[j],
                degrees_of_freedom=4 if self.likelihood == "student" else None,
                base_logvolume=sum(p["volume"] for p in pieces),
            )
            z = result["residual"]
            probability = 1.0
            if self.likelihood == "mixture":
                signal = float(z @ z)
                clutter = 2 * self.group_points[j] * np.log(PERIOD / (np.sqrt(2 * np.pi) * 150))
                log_signal = np.log(0.95) - signal / 2
                log_clutter = np.log(0.05) - clutter / 2
                total = np.logaddexp(log_signal, log_clutter)
                probability = float(np.exp(log_signal - total))
                z = z * np.sqrt((-2 * total) / signal)
            residuals.append(z)
            coefficients[j] = result["coefficient"]
            statistics[j] = dict(
                norad=int(self.scan.norads[j]),
                points=self.group_points[j],
                quadratic=result["quadratic"],
                logvolume=result["logvolume"],
                cost=float(z @ z),
                signal_probability=probability,
                coefficient=result["coefficient"],
            )
        # Preserve the parent's prior order so the RX-coordinate wrapper can
        # replace exactly its four radio priors without touching orbit priors.
        residuals.append(state["beta"][4:8] / 75)
        residuals.append(state["phases"][self.labels] / self.scan.sigma[self.labels])
        for extra in state["extra"].values():
            residuals.append(extra / (10 if self.method == "family_rate" else 1e-4))
        if self.method == "receiver_smooth":
            residuals.append(state["smooth"].ravel() / 200)
        below = np.maximum(0, -e) / 2
        residuals.insert(0, below)
        return np.concatenate(residuals), statistics, coefficients, state, f, e, modes

    def residual(self, x, *, details=False):
        r, statistics, *_ = self.calculate(x)
        return (r, list(statistics.values())) if details else r

    def association_state(self, x):
        _, statistics, coefficients, state, *_ = self.calculate(x)
        state["marginal_orbit_coefficients"] = {j: coefficients[j] for j in self.supported}
        if self.satellite_bias_sigma:
            state["marginal_orbit_coefficients"] = {
                j: coefficients[j][: self.rank] for j in self.supported
            }
            state["marginal_satellite_bias_hz"] = {
                j: float(a[-1] * self.satellite_bias_sigma) for j, a in coefficients.items()
            }
        state["marginal_signal_probability"] = {
            j: v["signal_probability"] for j, v in statistics.items()
        }
        return state

    def predicted(self, x):
        if not self.ready:
            return super().predicted(x)
        _, _, coefficients, state, nominal, e, modes = self.calculate(x)
        f = nominal.copy()
        if self.mode_bank is not None:
            sky = {k: v.copy() for k, v in self.orbit_sky(state).items()}
            dp = self.mode_bank["position_km"].reshape(len(self.labels), self.rank, -1, 3)
            dv = self.mode_bank["velocity_km_s"].reshape(len(self.labels), self.rank, -1, 3)
            for j in self.supported:
                k = self.local_j[j]
                a = coefficients[j][: self.rank]
                sky["position_km"][k] += np.einsum("k,ktd->td", a, dp[k])
                sky["velocity_km_s"][k] += np.einsum("k,ktd->td", a, dv[k])
            f, e = paired_phase_frequency(
                sky, self.flat_times, self.flat_labels, state["phases"][self.labels], *latlon(x[:2])
            )
            if self.method == "family_rate":
                for j, a in state["extra"].items():
                    use = self.flat_labels == self.local_j[j]
                    f[use] += a[0] * (self.flat_times[use] - 150)
        if self.satellite_bias_sigma:
            for j, a in coefficients.items():
                f[self.flat_labels == self.local_j[j]] += a[-1] * self.satellite_bias_sigma
        return f, e


def marginal_problem(
    *args, kind, likelihood, scale=1.0, curve_bias_sigma=1000.0, satellite_bias_sigma=0.0
):
    return ReceiverDriftProblem(
        MarginalFamilies(
            *args,
            kind=kind,
            likelihood=likelihood,
            scale=scale,
            curve_bias_sigma=curve_bias_sigma,
            satellite_bias_sigma=satellite_bias_sigma,
        ),
        mean_sigma=10,
    )


def variant_options(variant):
    likelihood, kind = variant.split("_", 1)
    options = dict(kind=kind, likelihood=likelihood)
    if likelihood in ("hierarchy", "widebias"):
        options.update(
            likelihood="student",
            curve_bias_sigma=300.0,
            satellite_bias_sigma=1000.0 if likelihood == "hierarchy" else 5000.0,
        )
    return options


def run(case, method, variants=VARIANTS):
    directory = OUTPUT / "marginal" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source = SOURCE / case / f"{method}_center.json"
    seed = json.loads(source.read_text())
    scan = Scan(case)
    protocol_path = directory / "protocol.json"
    previous_protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else {}
    per_variant = previous_protocol.get(
        "source_by_variant",
        {v: previous_protocol.get("code_sha256") for v in previous_protocol.get("variants", [])},
    )
    for v in variants:
        if not all(f"{v}/{a}" in results for a in ("c0", "fitted_c")):
            per_variant[v] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_parameters=True,
            main_mean_is_latest_causal_orbit=True,
            only_original_individually_curved_points_calibrate_or_locate=True,
            modes_require_two_curved_RX_channel_owners=True,
            posterior_frequency_predictions_are_not_new_validated_SGP4_TLEs=True,
            covariance_scale_from_successive_causal_disagreement_not_calibrated_covariance=True,
            bias_sigma_hz=1000,
            noise_sigma_hz=150,
            student_nu=4,
            mixture_signal_prior=0.95,
            radial_floor_km=0.05,
            cross_track_floor_km=0.025,
            missing_prior_radial_km=0.5,
            missing_prior_cross_km=0.25,
            marginal_logdet_complexity_in_objective=True,
            no_new_fitted_mode_coordinates=True,
            common_c0_nominations_aliases_geographic_starts_and_24_iteration_budgets=True,
            unweighted_full_observation_family_likelihood=True,
            variants=sorted(set(previous_protocol.get("variants", [])) | set(variants)),
            source_by_variant=per_variant,
            options_by_variant={v: variant_options(v) for v in per_variant},
            seed_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for variant in variants:
        if all(f"{variant}/{a}" in results for a in ("c0", "fitted_c")):
            continue
        options = variant_options(variant)

        def factory(*args, config=options):
            return marginal_problem(*args, **config)

        fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
        for arm, fit in fits.items():
            p = factory(scan, seed, method, arm == "fitted_c", (0, 0))
            x = np.array(min(fit["fits"], key=lambda f: f["score"])["parameters"])
            fit["state"] = p.association_state(x)
            native = p.native_parameters(x)
            fit["marginal_statistics"] = p.problem.calculate(native)[1]
            fit["mode_metadata"] = p.mode_metadata
            results[f"{variant}/{arm}"] = fit
        write(path, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    variant=variant,
                    positions={a: f["east_north_km"].tolist() for a, f in fits.items()},
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    p.add_argument("--method", choices=METHODS, default="shared_phase")
    p.add_argument("--variants", nargs="+", default=VARIANTS)
    a = p.parse_args()
    run(a.case, a.method, tuple(a.variants))
