"""Bounded physical-orbit and receiver-clock diagnostics for S01 CH2 T000."""

import json
from types import SimpleNamespace

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import BRACKET, NORAD, OUTPUT, PROTOTYPES, TARGET, hardware
from fit_s01_69333_tle_parameter import perturb
from inventory_clipped_phase_cohort import ROOT, load_study
from run_s01_shared_satellite_prototypes import Prototype
from sgp4.api import Satrec

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_satellite_correction import profile_curve
from leo.sky.propagation import ElementSetCatalogue

DESTINATION = OUTPUT / "orbit_timing"
MODELS = dict(
    phase_only=0.0,
    mean_motion_rev_day=0.01,
    inclination_deg=0.05,
    raan_deg=0.05,
    e_cos_omega=0.0005,
    e_sin_omega=0.0005,
    bstar=0.001,
    rx1_clock_offset_s=1.0,
    rx1_clock_rate_100ppm=100.0,
    rx1_clock_rate_5000ppm=5000.0,
)


def warp(model, delta, times, receiver, reference):
    """Positive correction means the actual observation happened later."""
    times = np.asarray(times)
    if receiver != 1:
        return times
    if model == "rx1_clock_offset_s":
        return times + delta
    if model.startswith("rx1_clock_rate_"):
        return times + delta * 1e-6 * (times - reference)
    return times


class Investigation:
    def __init__(self):
        self.source = json.loads((BRACKET / "bracketing_tles.json").read_text())
        self.origin = self.source["anchor_utc_ns"]
        self.base = Satrec.twoline2rv(*self.source["past"][str(NORAD)]["lines"])
        self.arms = {}
        for fc in (False, True):
            arm = "fitted_c" if fc else "c0"
            study, *_ = load_study("DSX01-S01", fc)
            previous = json.loads(
                (PROTOTYPES / "family_extension" / arm / "association.json").read_text()
            )["rows"]
            old = {r["component"]: r for r in previous}
            tracks = [t for t in study.tracks if old[t["key"]]["candidate_norad"] == NORAD]
            fit = json.loads(
                (
                    ROOT / "reports/2026_10_17_s01_phase_sensitivity" / arm / "fit_cap_2.7.json"
                ).read_text()
            )
            beta = np.array(fit["beta"])
            self.arms[arm] = dict(
                tracks=tracks,
                beta=beta,
                old=old,
                y=[t["values"] - hardware(t, beta) for t in tracks],
            )
            self.curved = [i for i, t in enumerate(tracks) if t["key"] in study.curved_keys]
            self.phase = float(fit["phases_s"][np.flatnonzero(study.sky["norad"] == NORAD)[0]])
        self.tracks = self.arms["c0"]["tracks"]
        assert [t["key"] for t in self.tracks] == [
            t["key"] for t in self.arms["fitted_c"]["tracks"]
        ]
        self.target = next(i for i, t in enumerate(self.tracks) if t["key"] == TARGET)
        self.times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        self.reference = float(
            np.median(np.concatenate([self.tracks[i]["times"] for i in self.curved]))
        )
        self.knots = np.arange(np.floor(min(self.times)) - 20, np.ceil(max(self.times)) + 21)
        self.index = [np.searchsorted(self.times, t["times"]) for t in self.tracks]
        self.cases = dict(
            target_only=[self.target],
            all_curved=self.curved,
            omit_target=[i for i in self.curved if i != self.target],
        )
        self.cache = {}

    def satellite(self, model, delta):
        return (
            perturb(self.base, model, delta)
            if model
            in (
                "mean_motion_rev_day",
                "inclination_deg",
                "raan_deg",
                "e_cos_omega",
                "e_sin_omega",
                "bstar",
            )
            else self.base
        )

    def frequencies(self, model, delta, phases, exact=False):
        sat = self.satellite(model, delta)
        if exact:
            proxy = SimpleNamespace(
                method="family_extension",
                origin=self.origin,
                satellites={NORAD: sat},
                tref={NORAD: self.reference},
            )
            output = []
            elevations = []
            for receiver in (1, 2):
                t = warp(model, delta, self.times, receiver, self.reference)
                f, e = Prototype.forward(proxy, NORAD, np.array([phases[0], 0.0]), t)
                output.append(f[None, :])
                elevations.append(e[None, :])
            return np.array(output), np.array(elevations)
        key = model, round(float(delta), 14)
        if key not in self.cache:
            cat = ElementSetCatalogue((str(NORAD),), (NORAD,), (sat,))
            p, v, usable = matching.ecef_states(cat, self.origin, self.knots)
            assert usable.all()
            self.cache[key] = dict(time_s=self.knots, position_km=p, velocity_km_s=v)
        sky = self.cache[key]
        many = dict(
            time_s=self.knots,
            position_km=np.broadcast_to(sky["position_km"], (len(phases), len(self.knots), 3)),
            velocity_km_s=np.broadcast_to(sky["velocity_km_s"], (len(phases), len(self.knots), 3)),
        )
        output, elevations = [], []
        for receiver in (1, 2):
            t = warp(model, delta, self.times, receiver, self.reference)
            geom = prepare_phase_geometry(many, t, np.array(phases))
            f, e, _ = phase_linear_frequency(geom, matching.LATITUDE, matching.LONGITUDE)
            output.append(f)
            elevations.append(e)
        return np.array(output), np.array(elevations)

    def costs(self, f, arm):
        costs = []
        for i, t in enumerate(self.tracks):
            pred = t["rf_hz"] / 11.5e9 * f[t["receiver"] - 1][:, self.index[i]]
            terms = profile_curve(self.arms[arm]["y"][i], pred)
            costs.append(min(len(t["times"]), 50) * terms["score"])
        return np.array(costs)

    def result(self, model, best, arm, case):
        f, e = self.frequencies(model, best["delta"], [best["phase_s"]], exact=True)
        approx, _ = self.frequencies(model, best["delta"], [best["phase_s"]])
        error = float(np.max(abs(f - approx)))
        assert error < 1
        rows = []
        for i, t in enumerate(self.tracks):
            terms = profile_curve(
                self.arms[arm]["y"][i], t["rf_hz"] / 11.5e9 * f[t["receiver"] - 1, 0, self.index[i]]
            )
            noise = matching.noise_screen(terms["residual"][0], t["times"])
            visible = bool(np.min(e[t["receiver"] - 1, 0, self.index[i]]) >= 0)
            passing = bool(
                visible
                and terms["rms"][0] <= 450
                and abs(terms["bias"][0]) <= 3000
                and noise["noise_screen_pass"]
            )
            rows.append(
                dict(
                    component=t["key"],
                    points=len(t["times"]),
                    receiver=t["receiver"],
                    used_for_fit=i in self.cases[case],
                    active_curvature=i in self.curved,
                    passing=passing,
                    previously_accepted=self.arms[arm]["old"][t["key"]]["compatible"],
                    rms_hz=float(terms["rms"][0]),
                    bias_hz=float(terms["bias"][0]),
                    residual_hz=terms["residual"][0],
                    times_s=t["times"],
                    visible=visible,
                    diagnostics=noise,
                )
            )
        return dict(
            **best,
            model=model,
            arm=arm,
            fit_case=case,
            bound=MODELS[model],
            at_bound=bool(MODELS[model] and abs(best["delta"]) >= 0.99 * MODELS[model]),
            timing_reference_s=self.reference,
            interpolation_max_error_hz=error,
            rows=rows,
            calibration_members=[self.tracks[i]["key"] for i in self.cases[case]],
            target=rows[self.target],
            passing_points=sum(r["points"] for r in rows if r["passing"]),
            gained_points=sum(
                r["points"] for r in rows if r["passing"] and not r["previously_accepted"]
            ),
            lost_points=sum(
                r["points"] for r in rows if not r["passing"] and r["previously_accepted"]
            ),
        )

    def run(self):
        DESTINATION.mkdir(exist_ok=True)
        results = {}
        for model, bound in MODELS.items():
            best = {(arm, case): None for arm in self.arms for case in self.cases}
            phases = np.unique(np.r_[np.linspace(-15, 15, 121), self.phase])
            for delta in np.linspace(-bound, bound, 21) if bound else [0.0]:
                f, _ = self.frequencies(model, delta, phases)
                for arm in self.arms:
                    costs = self.costs(f, arm)
                    for case, members in self.cases.items():
                        score = costs[members].sum(axis=0)
                        j = int(np.argmin(score))
                        if best[arm, case] is None or score[j] < best[arm, case]["cost"]:
                            best[arm, case] = dict(
                                delta=float(delta), phase_s=float(phases[j]), cost=float(score[j])
                            )
            for (arm, case), winner in best.items():
                dstep, pstep = bound / 10, 0.25
                for _ in range(3):
                    anchor = winner.copy()
                    for delta in (
                        np.linspace(
                            max(-bound, anchor["delta"] - dstep),
                            min(bound, anchor["delta"] + dstep),
                            9,
                        )
                        if bound
                        else [0.0]
                    ):
                        center = anchor["phase_s"]
                        if model == "mean_motion_rev_day":
                            epoch = (
                                (self.base.jdsatepoch - 2440587.5) + self.base.jdsatepochF
                            ) * 86400
                            elapsed = self.origin / 1e9 + self.reference - epoch
                            center -= (
                                elapsed
                                / (self.base.no_kozai * 1440 / (2 * np.pi))
                                * (delta - anchor["delta"])
                            )
                        low, high = max(-15, center - pstep), min(15, center + pstep)
                        if high < low:
                            continue
                        phases = np.linspace(low, high, 9)
                        f, _ = self.frequencies(model, delta, phases)
                        scores = self.costs(f, arm)[self.cases[case]].sum(axis=0)
                        j = int(np.argmin(scores))
                        if scores[j] < winner["cost"]:
                            winner = dict(
                                delta=float(delta), phase_s=float(phases[j]), cost=float(scores[j])
                            )
                    dstep /= 4
                    pstep /= 4
                key = f"{arm}/{case}/{model}"
                results[key] = self.result(model, winner, arm, case)
            write(DESTINATION / "results.json", results)
            print(
                json.dumps(
                    dict(
                        model=model,
                        results={
                            key: dict(
                                delta=r["delta"],
                                phase_s=r["phase_s"],
                                target_rms=r["target"]["rms_hz"],
                                target_passes=r["target"]["passing"],
                                gained=r["gained_points"],
                                lost=r["lost_points"],
                                at_bound=r["at_bound"],
                            )
                            for key, r in results.items()
                            if r["model"] == model
                        },
                    )
                ),
                flush=True,
            )
            self.cache.clear()
        write(
            DESTINATION / "protocol.json",
            dict(
                target=TARGET,
                candidate_norad=NORAD,
                gps_and_hardware_frozen=True,
                future_tle_not_used_in_fits=True,
                linear_calibration=False,
                phase_bound_s=15,
                parameter_bounds=MODELS,
                curved_members=[self.tracks[i]["key"] for i in self.curved],
                search=(
                    "21 parameter × 122 phase coarse grid; three 9×9 local refinements per arm/case"
                ),
                c0_fitted_c_same_observations_candidates_bounds_search_budgets=True,
                clock_definition="actual time = recorded time + RX1 correction; RX2 unchanged",
                orbital_phase_definition="satellite advance at fixed observer Earth orientation",
                per_curve_constant_sigma_hz=1000,
                curve_weight_point_cap=50,
                target_only_is_diagnostic_not_calibration=True,
                omitted_curve_transfer_conditional_on_preexisting_hardware=True,
                box_constraints_are_diagnostic_not_validated_orbit_or_clock_priors=True,
                no_association_changed=True,
            ),
        )


if __name__ == "__main__":
    Investigation().run()
