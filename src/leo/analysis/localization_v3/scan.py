"""Scan likelihood over explicitly supplied native tracks and causal orbit evidence.

Extracted mathematical operations retain the original calibration/alias/gating
rules. No historical workers, paths, archive readers or evaluation coordinates
are imported. This is a scoring component, not yet the full position optimizer.
"""
from copy import deepcopy

import numpy as np
from sgp4.api import WGS72, Satrec

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.tracks import active_curvature
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import (
    profile,
    projected_receiver_basis,
    whitening,
)
from leo.sky.propagation import ElementSetCatalogue


def group(track):
    return 2 * (track["receiver"] - 1) + int(track["channel"] > 4)


def perturb(base, parameter, delta):
    """Keep epoch and mean argument of latitude fixed when varying e-vector."""
    e, omega, mean = base.ecco, base.argpo, base.mo
    inclination, node, motion, bstar = base.inclo, base.nodeo, base.no_kozai, base.bstar
    if parameter in ("e_cos_omega", "e_sin_omega"):
        ex, ey = e * np.cos(omega), e * np.sin(omega)
        ex += delta if parameter == "e_cos_omega" else 0
        ey += delta if parameter == "e_sin_omega" else 0
        e = float(np.hypot(ex, ey))
        if delta != 0:
            new_omega = float(np.arctan2(ey, ex) % (2 * np.pi))
            mean = float((mean + omega - new_omega) % (2 * np.pi))
            omega = new_omega
    elif parameter == "mean_motion_rev_day":
        motion += delta * 2 * np.pi / 1440
    elif parameter == "inclination_deg":
        inclination += np.deg2rad(delta)
    elif parameter == "raan_deg":
        node += np.deg2rad(delta)
    elif parameter == "bstar":
        bstar += delta
    elif parameter != "phase_only":
        raise ValueError(parameter)
    sat = Satrec()
    sat.sgp4init(WGS72, base.operationmode, base.satnum,
                 (base.jdsatepoch - 2433281.5) + base.jdsatepochF,
                 bstar, base.ndot, base.nddot, e, omega, inclination, mean, motion, node)
    # Preserve the exact split epoch rather than accepting float date rounding.
    sat.jdsatepoch, sat.jdsatepochF = base.jdsatepoch, base.jdsatepochF
    return sat


class ScanLikelihood:
    def __init__(self, tracks, bank, elements, *, origin_utc_ns, regional_center, noise,
                 search_region=None, previous_tle=None, previous_tle_sha256=None,
                 noise_sha256=None):
        if not tracks:
            raise ValueError("Nonempty prepared tracks required")
        self.origin_utc_ns = origin_utc_ns
        self.search_region = search_region
        self.previous_tle = previous_tle
        self.previous_tle_sha256 = previous_tle_sha256
        self.sky = {key: np.array(value, copy=True) for key, value in bank.items()}
        self.tracks = deepcopy(tracks)
        for track in self.tracks:
            track["times"], track["values"] = np.array(track["times"]), np.array(track["values"])
        self.curved = [i for i, track in enumerate(self.tracks) if active_curvature(track)]
        self.times = np.unique(np.concatenate([track["times"] for track in self.tracks]))
        self.index = [np.searchsorted(self.times, track["times"]) for track in self.tracks]
        self.groups = [(self.tracks[i]["key"], [self.tracks[i]]) for i in self.curved]
        self.geometry = prepare_phase_geometry(self.sky, self.times)
        self.norads, self.sigma = self.sky["norad"], self.sky["phase_sigma_s"]
        self.initial = np.zeros(8)
        self.center = list(regional_center)
        self.scale = 111.32 * np.cos(np.deg2rad(self.center[0]))
        self.white = [whitening(t["times"]) for t in self.tracks]
        self.ou = [whitening(t["times"], correlated_sigma_hz=150., correlation_seconds=10.)
                   for t in self.tracks]
        self.rx_basis = [projected_receiver_basis(t["times"]) for t in self.tracks]
        self.reference, self.element_derivatives = {}, {}
        self.elements = deepcopy(elements)
        self.fixed_window_noise = deepcopy(noise)
        self.fixed_window_noise_sha256 = noise_sha256
        self.radio_sigma_hz = noise["constant_radio_sigma_hz"]

    def latlon(self, xy):
        return self.center[0] + xy[1] / 111.0, self.center[1] + xy[0] / self.scale

    def shifted(self, base, phases, point, extra=None):
        f, e, h = (x.copy() for x in base)
        active = np.flatnonzero(abs(phases) > 1e-9)
        if extra:
            active = np.union1d(active, list(extra))
        if len(active):
            sky = dict(
                time_s=self.sky["time_s"],
                position_km=self.sky["position_km"][active].copy(),
                velocity_km_s=self.sky["velocity_km_s"][active].copy(),
            )
            if extra:
                for k, j in enumerate(active):
                    if j in extra:
                        dp, dv = self.element_basis(int(j))
                        sky["position_km"][k] += np.einsum("k,ktd->td", extra[j], dp)
                        sky["velocity_km_s"][k] += np.einsum("k,ktd->td", extra[j], dv)
            geometry = prepare_phase_geometry(sky, self.times, phases[active])
            f[active], e[active], h[active] = phase_linear_frequency(geometry, *self.latlon(point))
        return f, e, h

    def element_basis(self, j):
        if j not in self.element_derivatives:
            n = int(self.norads[j])
            sat = Satrec.twoline2rv(*self.elements[str(n)]["lines"])
            rows = []
            for parameter in ("e_cos_omega", "e_sin_omega"):
                cat = ElementSetCatalogue(
                    (str(n), str(n)),
                    (n, n),
                    tuple(perturb(sat, parameter, d) for d in (2e-5, -2e-5)),
                )
                p, v, good = ecef_states(
                    cat, self.origin_utc_ns, self.sky["time_s"]
                )
                assert good.all()
                rows.append(((p[0] - p[1]) / 4e-5, (v[0] - v[1]) / 4e-5))
            self.element_derivatives[j] = (
                np.array([r[0] for r in rows]),
                np.array([r[1] for r in rows]),
            )
        return self.element_derivatives[j]

    def hardware(self, t, beta):
        g = group(t)
        v = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
        if len(beta) == 9:
            v += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
        return v

    def curve(self, i, y, predicted, method, *, shortlist=False):
        t = self.tracks[i]
        w, volume = self.ou[i] if method == "correlated_noise" else self.white[i]
        terms = profile(y, predicted, w, volume)
        possible = np.flatnonzero((terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000))
        passing = np.zeros(len(terms["bias"]), bool)
        if len(possible):
            checked = batch_noise_screen(terms["innovations"][possible], t["times"])
            passing[possible] = checked["noise_screen_pass"]
        diagnostics = dict(noise_screen_pass=passing.copy())
        result = dict(
            terms,
            passing=passing,
            parts=np.ones(len(terms["bias"]), int),
            split_at=np.full(len(terms["bias"]), -1, int),
            diagnostics=diagnostics,
        )
        if (
            method != "penalized_split"
            or shortlist
            or i not in self.curved
            or np.ptp(t["times"]) < 40
        ):
            return result
        candidates = np.argsort(terms["cost"])[:3]
        f = np.atleast_2d(predicted)
        for cut in range(10, len(y) - 9):
            masks = [slice(0, cut), slice(cut, None)]
            if not all(
                active_curvature(dict(times=t["times"][m], values=t["values"][m])) for m in masks
            ):
                continue
            parts = []
            for m in masks:
                inv, vol = whitening(t["times"][m])
                p = profile(y[m], f[candidates, m], inv, vol)
                d = batch_noise_screen(p["innovations"], t["times"][m])
                p["passing"] = d["noise_screen_pass"] & (p["rms"] <= 450) & (abs(p["bias"]) <= 3000)
                parts.append(p)
            cost = parts[0]["cost"] + parts[1]["cost"] + 12 + np.log(len(y))
            for k, j in enumerate(candidates):
                if (
                    cost[k] < result["cost"][j]
                    and parts[0]["passing"][k]
                    and parts[1]["passing"][k]
                ):
                    for key in ("residual", "innovations"):
                        result[key][j] = np.r_[parts[0][key][k], parts[1][key][k]]
                    result["cost"][j] = cost[k]
                    result["rms"][j] = np.sqrt(np.mean(result["residual"][j] ** 2))
                    result["bias"][j] = max(abs(parts[0]["bias"][k]), abs(parts[1]["bias"][k]))
                    result["passing"][j], result["parts"][j], result["split_at"][j] = True, 2, cut
        return result

    def predictions(self, state, base, point, method):
        f, e, h = self.shifted(
            base, state["phases"], point, state["extra"] if method == "orbit_em" else None
        )
        if method == "family_rate":
            for j, rate in state["extra"].items():
                f[j] += rate[0] * (self.times - self.reference.get(j, 150.0))
        return f, e, h

    def association(self, state, base, point, method, *, all_tracks=False):
        f, e, h = self.predictions(state, base, point, method)
        rows, nominated, feasible = [], {}, {}
        objective = 0.0
        selected = range(len(self.tracks)) if all_tracks else self.curved
        for i in selected:
            t, ix = self.tracks[i], self.index[i]
            y = t["values"] - self.hardware(t, state["beta"])
            if method == "receiver_smooth":
                y -= t["rf_hz"] / 11.5e9 * self.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
            terms = self.curve(i, y, t["rf_hz"] / 11.5e9 * f[:, ix], method)
            visible = e[:, ix].min(axis=1) >= 0
            good = terms["passing"] & visible
            feasible[i] = good.copy()
            choice = (
                int(np.argmin(np.where(good, terms["cost"], np.inf)))
                if good.any()
                else int(np.argmin(np.where(visible, terms["cost"], np.inf)))
            )
            nomination = int(np.argmin(np.where(visible, terms["cost"], np.inf)))
            nominated[i] = dict(j=nomination, terms=terms, y=y)
            if i in self.curved:
                objective += min(len(y), 50) * (
                    min(terms["cost"][choice] / len(y), 36) if good.any() else 36
                )
            rows.append(
                dict(
                    component=t["key"],
                    points=len(y),
                    candidate_norad=int(self.norads[choice]),
                    candidate_index=choice,
                    compatible=bool(good.any()),
                    active_curvature=i in self.curved,
                    rms_hz=float(terms["rms"][choice]),
                    bias_hz=float(terms["bias"][choice]),
                    cost=float(terms["cost"][choice]),
                    parts=int(terms["parts"][choice]),
                    split_at=int(terms["split_at"][choice]),
                    feasible_candidates=int(good.sum()),
                    residual_hz=terms["residual"][choice].copy(),
                    innovations_hz=terms["innovations"][choice].copy(),
                    times_s=t["times"],
                )
            )
        # Extra satellite corrections need two accepted curved channels.
        # Linear fragments can receive calibration but never create ownership.
        for _ in range(3):
            owners = {}
            for r in rows:
                if r["compatible"] and r["active_curvature"]:
                    i = next(k for k in selected if self.tracks[k]["key"] == r["component"])
                    owners.setdefault(r["candidate_index"], set()).add(self.tracks[i]["channel"])
            forbidden = {j for j in state["extra"] if len(owners.get(j, set())) < 2}
            changed = False
            supported_groups = {
                group(self.tracks[i])
                for i in selected
                if i in self.curved
                and any(r["component"] == self.tracks[i]["key"] and r["compatible"] for r in rows)
            }
            for i, r in zip(selected, rows, strict=True):
                good = feasible[i]
                if forbidden:
                    good[list(forbidden)] = False
                if i not in self.curved:
                    if group(self.tracks[i]) not in supported_groups:
                        good[:] = False
                    unsupported = abs(state["phases"]) > 0.001
                    unsupported[list(owners)] = False
                    good[unsupported] = False
                terms = nominated[i]["terms"]
                if good.any():
                    j = int(np.argmin(np.where(good, terms["cost"], np.inf)))
                    passing = True
                else:
                    j, passing = r["candidate_index"], False
                changed |= (j, passing) != (r["candidate_index"], r["compatible"])
                r.update(
                    candidate_index=j,
                    candidate_norad=int(self.norads[j]),
                    compatible=passing,
                    rms_hz=float(terms["rms"][j]),
                    bias_hz=float(terms["bias"][j]),
                    cost=float(terms["cost"][j]),
                    parts=int(terms["parts"][j]),
                    split_at=int(terms["split_at"][j]),
                    feasible_candidates=int(good.sum()),
                    residual_hz=terms["residual"][j].copy(),
                    innovations_hz=terms["innovations"][j].copy(),
                )
            if not changed:
                break
        objective = sum(
            min(r["points"], 50) * (min(r["cost"] / r["points"], 36) if r["compatible"] else 36)
            for r in rows
            if r["active_curvature"]
        )
        objective += np.sum((state["beta"][4:8] / 75) ** 2)
        objective += np.sum((state["phases"] / self.sigma) ** 2)
        for extra in state["extra"].values():
            objective += float(np.sum((extra / (10.0 if method == "family_rate" else 1e-4)) ** 2))
        if method == "receiver_smooth":
            objective += float(np.sum((state["smooth"] / 200) ** 2))
        dimension = len(state["beta"]) + np.count_nonzero(abs(state["phases"]) > 1e-6)
        dimension += sum(len(x) for x in state["extra"].values())
        if method == "receiver_smooth":
            dimension += state["smooth"].size
        objective += dimension * np.log(
            max(2, sum(len(self.tracks[i]["times"]) for i in self.curved))
        )
        return float(objective), rows, nominated, (f, e, h)
