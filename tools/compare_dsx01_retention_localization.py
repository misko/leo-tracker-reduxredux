"""Matched bounded geographic comparison of six curved-only retention models.

No supplied evaluation coordinate or fixed-GPS satellite assignment enters fitting.
The common regional search is deliberately bounded and is not global convergence.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from evaluate_shared_satellite_phase import solve_joint
from fit_s01_69333_tle_parameter import perturb
from localize_merged_track_catalogue import raw_curvature
from sgp4.api import Satrec

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import (
    PERIOD,
    add_curve,
    profile,
    projected_receiver_basis,
    whitening,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, box_quadratic
from leo.analysis.research.shared_satellite_correction import soft_curve_responsibilities
from leo.sky.propagation import ElementSetCatalogue

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_18_dsx01_retention_localization"
PARTITION = ROOT / "reports/2026_10_17_robust_curve_reassociation/partition"
METHODS = (
    "shared_phase",
    "family_rate",
    "orbit_em",
    "penalized_split",
    "correlated_noise",
    "receiver_smooth",
)


class Scan:
    def __init__(self, case):
        self.case = case
        self.bank_path = (
            ROOT
            / (
                "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs"
                if case.endswith("S01")
                else "reports/2026_10_17_robust_curve_reassociation/frozen_inputs"
            )
            / case
        )
        self.recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
        self.receipt = json.loads((self.bank_path / "receipt.json").read_text())
        assert self.receipt["reference_position_used"] is False
        self.sky = dict(np.load(self.bank_path / "bank.npz"))
        assert (
            hashlib.sha256((self.bank_path / "bank.npz").read_bytes()).hexdigest()
            == self.receipt["bank_sha256"]
        )
        self.tracks = json.loads((PARTITION / case / "curves.json").read_text())
        for t in self.tracks:
            t["times"], t["values"] = np.array(t["times"]), np.array(t["values"])
        self.curved = [i for i, t in enumerate(self.tracks) if raw_curvature(t)]
        self.times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        self.index = [np.searchsorted(self.times, t["times"]) for t in self.tracks]
        self.groups = [(self.tracks[i]["key"], [self.tracks[i]]) for i in self.curved]
        self.geometry = prepare_phase_geometry(self.sky, self.times)
        self.norads = self.sky["norad"]
        self.sigma = np.maximum(1.0, self.sky["phase_sigma_s"])
        # Older radio calibrations can contain linear-track votes, even as seeds.
        self.initial = np.zeros(8)
        self.center = self.receipt["regional_center"]
        self.scale = 111.32 * np.cos(np.deg2rad(self.center[0]))
        self.white = [whitening(t["times"]) for t in self.tracks]
        self.ou = [
            whitening(t["times"], correlated_sigma_hz=150.0, correlation_seconds=10.0)
            for t in self.tracks
        ]
        self.rx_basis = [projected_receiver_basis(t["times"]) for t in self.tracks]
        self.reference = {}
        element_path = (
            ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "nominal_elements.json"
        )
        from dsx01_inference_audit import audit_scan_inputs, load_isolated_catalogue

        self.elements = load_isolated_catalogue(element_path, self.receipt, self.norads)
        self.element_input_path = element_path
        self.inference_input_audit = audit_scan_inputs(self)
        self.element_derivatives = {}

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
                p, v, good = matching.ecef_states(
                    cat, self.receipt["origin_utc_ns"], self.sky["time_s"]
                )
                assert good.all()
                rows.append(((p[0] - p[1]) / 4e-5, (v[0] - v[1]) / 4e-5))
            self.element_derivatives[j] = (
                np.array([r[0] for r in rows]),
                np.array([r[1] for r in rows]),
            )
        return self.element_derivatives[j]

    def hardware(self, t, beta):
        g = matching.group(t)
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
                raw_curvature(dict(times=t["times"][m], values=t["values"][m])) for m in masks
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
                matching.group(self.tracks[i])
                for i in selected
                if i in self.curved
                and any(r["component"] == self.tracks[i]["key"] and r["compatible"] for r in rows)
            }
            for i, r in zip(selected, rows, strict=True):
                good = feasible[i]
                if forbidden:
                    good[list(forbidden)] = False
                if i not in self.curved:
                    if matching.group(self.tracks[i]) not in supported_groups:
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

    def update(self, state, nominated, predicted, point, method):
        beta = state["beta"]
        families, membership_weight = {}, {}
        for i, r in nominated.items():
            if method == "orbit_em":
                t, terms = self.tracks[i], r["terms"]
                visible = predicted[1][:, self.index[i]].min(axis=1) >= 0
                responsibility, _ = soft_curve_responsibilities(
                    terms["cost"] * 150**2 / len(t["times"]),
                    terms["rms"],
                    terms["bias"],
                    visible,
                    len(t["times"]),
                )
                candidates = np.flatnonzero(
                    (responsibility > 0.01) & (terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000)
                )
            else:
                candidates = [r["j"]]
                responsibility = np.ones(len(self.norads))
            for j in candidates:
                if r["terms"]["rms"][j] <= 450 and abs(r["terms"]["bias"][j]) <= 3000:
                    families.setdefault(int(j), []).append(i)
                    membership_weight[i, int(j)] = float(responsibility[j])
        phases = sorted(families)
        phase_index = {j: len(beta) + k for k, j in enumerate(phases)}
        extra_index = {}
        size = len(beta) + len(phases)
        if method in ("family_rate", "orbit_em"):
            for j, members in families.items():
                if len({self.tracks[i]["channel"] for i in members}) >= 2:
                    count = 1 if method == "family_rate" else 2
                    extra_index[j] = list(range(size, size + count))
                    size += count
                    self.reference.setdefault(j, 150.0)
        smooth_index = {}
        if method == "receiver_smooth":
            for receiver in (1, 2):
                support = {
                    j
                    for j, members in families.items()
                    if any(self.tracks[i]["receiver"] == receiver for i in members)
                }
                if len(support) >= 2:
                    count = self.rx_basis[0].shape[1]
                    smooth_index[receiver] = list(range(size, size + count))
                    size += count
        normal, rhs = np.zeros((size, size)), np.zeros(size)
        current = np.zeros(size)
        current[: len(beta)] = beta
        for j, k in phase_index.items():
            current[k] = state["phases"][j]
        for j, indexes in extra_index.items():
            current[indexes] = state["extra"].get(j, np.zeros(len(indexes)))
        for receiver, indexes in smooth_index.items():
            current[indexes] = state["smooth"][receiver - 1]
        f, _, h = predicted
        element_features = {}
        for j in extra_index if method == "orbit_em" else []:
            columns = []
            for k in range(2):
                values = []
                for direction in (1, -1):
                    extra = {n: v.copy() for n, v in state["extra"].items()}
                    v = extra.setdefault(j, np.zeros(2))
                    v[k] += direction * 2e-5
                    sky = dict(
                        time_s=self.sky["time_s"],
                        position_km=self.sky["position_km"][[j]].copy(),
                        velocity_km_s=self.sky["velocity_km_s"][[j]].copy(),
                    )
                    dp, dv = self.element_basis(j)
                    sky["position_km"][0] += np.einsum("k,ktd->td", v, dp)
                    sky["velocity_km_s"][0] += np.einsum("k,ktd->td", v, dv)
                    geom = prepare_phase_geometry(sky, self.times, np.array([state["phases"][j]]))
                    values.append(phase_linear_frequency(geom, *self.latlon(point))[0][0])
                columns.append((values[0] - values[1]) / 4e-5)
            element_features[j] = np.array(columns)
        for j, members in families.items():
            for i in members:
                t, ix = self.tracks[i], self.index[i]
                q, g = t["rf_hz"] / 11.5e9, matching.group(t)
                design = np.zeros((len(t["times"]), size))
                design[:, g], design[:, g + 4] = 1, (t["times"] - 150) / 150
                if len(beta) == 9:
                    design[:, 8] = t["rf_hz"] / 1e9 - 11.5
                design[:, phase_index[j]] = q * h[j, ix]
                if j in extra_index:
                    design[:, extra_index[j]] = (
                        (q * (t["times"] - self.reference[j]))[:, None]
                        if method == "family_rate"
                        else q * element_features[j][:, ix].T
                    )
                if t["receiver"] in smooth_index:
                    design[:, smooth_index[t["receiver"]]] = q * self.rx_basis[i]
                raw = t["values"] - self.hardware(t, beta) - q * f[j, ix]
                if method == "receiver_smooth":
                    raw -= q * self.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
                raw += round(-float(raw.mean()) / PERIOD) * PERIOD
                values = raw + design @ current
                cut = int(nominated[i]["terms"]["split_at"][j])
                blocks = (
                    [slice(0, cut), slice(cut, None)]
                    if method == "penalized_split" and cut > 0
                    else [slice(None)]
                )
                for block in blocks:
                    w = (
                        self.ou[i][0]
                        if method == "correlated_noise"
                        else whitening(t["times"][block])[0]
                    )
                    add_curve(
                        normal,
                        rhs,
                        design[block],
                        values[block],
                        w,
                        min(1.0, 50 / len(t["times"])) * membership_weight[i, j],
                    )
        lower, upper = np.full(size, -np.inf), np.full(size, np.inf)
        normal += np.eye(size) * 1e-12
        for g in range(4):
            normal[g + 4, g + 4] += 1 / 75**2
            lower[g + 4], upper[g + 4] = -150, 150
        if len(beta) == 9:
            lower[8], upper[8] = -200000, 200000
        for j, k in phase_index.items():
            normal[k, k] += 1 / self.sigma[j] ** 2
            lower[k], upper[k] = -15, 15
        for _j, indexes in extra_index.items():
            scale, bound = (10.0, 20.0) if method == "family_rate" else (1e-4, 0.0005)
            normal[indexes, indexes] += 1 / scale**2
            lower[indexes], upper[indexes] = -bound, bound
        for indexes in smooth_index.values():
            normal[indexes, indexes] += 1 / 200**2
        solution, converged = box_quadratic(normal, rhs, lower, upper)
        proposal = dict(
            beta=solution[: len(beta)],
            phases=np.zeros(len(self.norads)),
            extra={},
            smooth=np.zeros_like(state["smooth"]),
        )
        proposal["beta"][:4] = (proposal["beta"][:4] + PERIOD / 2) % PERIOD - PERIOD / 2
        for j, k in phase_index.items():
            proposal["phases"][j] = solution[k]
        for j, indexes in extra_index.items():
            proposal["extra"][j] = solution[indexes]
        for receiver, indexes in smooth_index.items():
            proposal["smooth"][receiver - 1] = solution[indexes]
        return proposal, converged

    def at_point(self, point, *, models=METHODS, rounds=2, all_tracks=False):
        lat, lon = self.latlon(point)
        base = phase_linear_frequency(self.geometry, lat, lon)
        stats = matching.statistics(
            self.groups,
            dict(time_s=self.times, doppler_0=base[0], elevation_deg=base[1]),
            {str(t["channel"]): 0.0 for t in self.tracks},
        )
        stats = augment_phase_statistics(stats, self.times, base[0], base[2])
        output = {}
        for fc in (False, True):
            initial = np.r_[self.initial, 0.0] if fc else self.initial.copy()
            seed = solve_joint(
                stats,
                initial,
                self.sigma,
                np.full(len(self.norads), 15.0),
                2,
                drift_sigma_hz_s=0.5,
                drift_bound_hz_s=1.0,
            )
            state0 = dict(
                beta=seed[1],
                phases=seed[2],
                extra={},
                smooth=np.zeros((2, self.rx_basis[0].shape[1])),
            )
            arm = "fitted_c" if fc else "c0"
            for method in models:
                state = {k: v.copy() if hasattr(v, "copy") else v for k, v in state0.items()}
                history, best = [], None
                for iteration in range(rounds + 1):
                    score, rows, nom, predicted = self.association(state, base, point, method)
                    history.append(
                        dict(
                            iteration=iteration,
                            score=score,
                            curved_points=sum(r["points"] for r in rows if r["compatible"]),
                        )
                    )
                    if best is None or score < best[0]:
                        best = score, state, rows
                    if iteration < rounds:
                        state, _ = self.update(state, nom, predicted, point, method)
                score, state, rows = best
                if all_tracks:
                    score, rows, _, _ = self.association(
                        state, base, point, method, all_tracks=True
                    )
                output[f"{arm}/{method}"] = dict(
                    score=score,
                    state=state,
                    rows=rows,
                    history=history,
                    latitude_deg=lat,
                    longitude_deg=lon,
                )
        return output


def run(case, *, smoke=False, locations=49):
    started = time.monotonic()
    scan = Scan(case)
    out = OUTPUT / case
    out.mkdir(exist_ok=True)
    if smoke:
        result = scan.at_point(np.array([0.0, 0.0]), rounds=1)
        write(out / "smoke.json", result)
        print(
            json.dumps(
                dict(
                    case=case,
                    elapsed_seconds=time.monotonic() - started,
                    scores={k: r["score"] for k, r in result.items()},
                )
            ),
            flush=True,
        )
        return
    cache, trace = {}, []

    def evaluate(point):
        point = np.asarray(point, float)
        if np.linalg.norm(point) > 250:
            return None
        key = tuple(np.round(point, 8))
        if key not in cache:
            if len(cache) >= locations:
                return None
            mark = time.monotonic()
            cache[key] = scan.at_point(point)
            trace.append(
                dict(
                    east_north_km=list(key),
                    elapsed_seconds=time.monotonic() - mark,
                    scores={k: r["score"] for k, r in cache[key].items()},
                )
            )
            write(out / "progress.json", trace)
            print(
                json.dumps(
                    dict(
                        case=case,
                        location=len(cache),
                        xy=list(key),
                        seconds=trace[-1]["elapsed_seconds"],
                    )
                ),
                flush=True,
            )
        return cache[key]

    for east in (-250.0, -125.0, 0.0, 125.0, 250.0):
        for north in (-250.0, -125.0, 0.0, 125.0, 250.0):
            if east * east + north * north <= 250**2:
                evaluate([east, north])
    for step in (25.0, 6.25, 1.5625, 0.390625):
        winners = []
        for method in METHODS:
            best = min(cache, key=lambda p: cache[p][f"c0/{method}"]["score"])
            if best not in winners:
                winners.append(best)
        chosen = [winners[0]]
        if len(winners) > 1:
            chosen.append(max(winners[1:], key=lambda p: np.linalg.norm(np.array(p) - chosen[0])))
        for center in chosen:
            for direction in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                evaluate(np.array(center) + step * np.array(direction))
    finalists = {}
    for key in cache[next(iter(cache))]:
        point = min(cache, key=lambda p: cache[p][key]["score"])
        finalists[key] = point
    exact = {}
    for point in set(finalists.values()):
        exact[point] = scan.at_point(point, rounds=3, all_tracks=True)
    endpoints = {key: exact[point][key] for key, point in finalists.items()}
    write(out / "endpoints.json", endpoints)
    write(
        out / "protocol.json",
        dict(
            case=case,
            location_budget=locations,
            locations=len(cache),
            same_geographic_candidates_for_all_models_and_c_arms=True,
            geographic_proposals_use_c0_scores_only=True,
            raw_curved_only_calibration=True,
            no_known_gps_fit_or_labels_used=True,
            inherited_hardware_or_position_seeds_used=False,
            hardware_initializer="all eight coefficients zero",
            cold_regional_search=True,
            regional_center=scan.center,
            radius_km=250,
            point_source_bank_sha256=scan.receipt["bank_sha256"],
            methods=METHODS,
            correlated_noise_sigma_hz=150,
            correlation_seconds=10,
            receiver_smooth_sigma_hz=200,
            satellite_rate_sigma_hz_s=10,
            satellite_rate_bound_hz_s=20,
            e_vector_sigma=1e-4,
            phase_bound_s=15,
            phase_sigma_floor_s=1,
            split_penalty="12+log(n), max 2 individually curved pieces",
            fixed_c0_and_fitted_c_search_budgets=True,
            global_optimum_proven=False,
            finalizer_rounds=3,
            geographic_rounds=2,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            elapsed_seconds=time.monotonic() - started,
        ),
    )
    print(
        json.dumps(
            dict(
                case=case,
                complete=True,
                locations=len(cache),
                elapsed_seconds=time.monotonic() - started,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S{i:02d}" for i in range(1, 6)])
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--locations", type=int, default=49)
    args = parser.parse_args()
    run(args.case, smoke=args.smoke, locations=args.locations)
