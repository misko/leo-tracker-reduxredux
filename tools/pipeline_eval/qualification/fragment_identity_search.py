"""Exhaustive causal/late search and a held-fragment prediction diagnostic."""

import argparse
import gzip
import json
from collections import defaultdict
from hashlib import sha256
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np
from sgp4.api import Satrec, SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)

from ..__main__ import encoded, save_json, write
from .association_orbit_diagnostic import affine_diagnostic, covariance, rms
from .fragment_identity_inputs import OUT
from .full_v5_check import _sha
from .input_factor_bridge import check, read
from .range_epoch_model import FOLD_HZ, LIGHT_KM_S, wrap

PHASES = np.linspace(-7.5, 7.5, 13)
LEVELS = ("L0", "L1", "L2", "L3", "L4r")
ARMS = ("c0", "fitted_c")
HORIZON = np.sin(np.deg2rad(-2))
WHITE_HZ = 150.0
ENVELOPE = 450.0


def verify(*files):
    for f in files:
        for name, digest in read(OUT / f)["files"].items():
            check(OUT / name, digest)


def states(sats, anchor, t, phases, site, up):
    time = anchor + np.rint(np.asarray(t) * 1e9).astype(np.int64)
    jd, frac = julian_day_from_utc_ns(time)
    angles = greenwich_mean_sidereal_time_rad(jd, frac)
    pool = SatrecArray(sats)
    phase_grid, visible = [], []
    for phase in phases:
        error, p, v = pool.sgp4(jd, frac + phase / 86400)
        p, v = teme_to_ecef(p, v, angles)
        d = p - site
        rho = np.linalg.norm(d, axis=-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            radial = np.sum(d * v, axis=-1) / rho
            elevation = (d @ up) / rho
        good = (error == 0).all(axis=1) & np.isfinite(radial).all(axis=1)
        phase_grid.append(radial)
        visible.append(np.where(good, np.min(elevation, axis=1), -2.0))
    return np.stack(phase_grid, axis=1), np.array(visible).T


def features(records, arm, order):
    receiver = np.asarray([r["rx"] - 1 for r in records])
    band = np.asarray([int(r["channel"] > 4) for r in records])
    times = np.asarray([r["time_s"] for r in records])
    rf = np.asarray([r["rf_hz"] for r in records])
    matrix = np.eye(4)[2 * receiver + band]
    terms = [matrix]
    prior = [20_000] * 4
    if order == 2:
        terms.append(np.eye(2)[receiver] * ((times - 150) / 100)[:, None])
        prior += [1500, 1500]
    if arm == "fitted_c":
        terms.append((rf / 1e9 - 11.5)[:, None])
        prior += [3000]
    return np.column_stack(terms), np.asarray(prior)


def hardware(selection, ledger, target):
    groups = defaultdict(dict)
    known = int(selection["chosen"]["owner"])
    for row in selection["independent_ownership"]:
        norad = int(row["v5_owner"])
        if norad != known and str(norad) in ledger:
            groups[norad].setdefault((row["component"], int(row["time_s"] // 2)), row)
    P = selection["proof"]
    site = geodetic_to_ecef_km(*P["position"], 0.0)
    up = ecef_to_enu_matrix(*P["position"])[2]
    anchor = P["metadata"]["anchor_utc_ns"]
    points, measured, group = [], [], []
    for norad, by_block in sorted(groups.items()):
        section = list(by_block.values())
        sat = Satrec.twoline2rv(*ledger[str(norad)]["lines"])
        phase_mean = selection["causal_phase_priors"].get(str(norad), [0])[0]
        radial, visibility = states(
            [sat], anchor, [r["time_s"] for r in section], [phase_mean], site, up
        )
        if visibility[0, 0] < HORIZON:
            continue
        for row, rate in zip(section, radial[0, 0], strict=True):
            points.append(row)
            measured.append(wrap(row["folded_hz"] + row["rf_hz"] * rate / LIGHT_KM_S, FOLD_HZ))
            group.append(norad)
    group, measured = np.asarray(group), np.asarray(measured)
    held = np.array(
        [int(sha256(f"calibration/{n}".encode()).hexdigest()[-3:], 16) % 5 == 0 for n in group],
        dtype=bool,
    )
    fits, predictions = {}, {}
    freedom = len(set(group[~held]))
    if freedom < 3 or len(set(group[held])) < 1:
        raise ValueError("independent clock calibration lacks separate satellite families")
    for arm in ARMS:
        fits[arm], predictions[arm] = {}, {}
        for i in (1, 2):
            X, scale = features(points, arm, i)
            X_target, _ = features(target, arm, i)
            coef = np.zeros(len(scale))
            for _ in range(6):
                residual = wrap(measured[~held] - X[~held] @ coef, FOLD_HZ)
                w = np.minimum(1, 1200 / np.maximum(abs(residual), 1e-6))
                inv = X[~held].T * w
                prior = (750 / scale) ** 2
                delta = np.linalg.solve(
                    inv @ X[~held] + np.diag(prior), inv @ residual - prior * coef
                )
                coef += delta
            pred = X_target @ coef
            fits[arm][f"L{i}"] = dict(
                coefficients=coef.tolist(),
                prior_sigma=scale.tolist(),
                rank=int(np.linalg.matrix_rank(X[~held])),
                family_train=len(set(group[~held])),
                family_held=len(set(group[held])),
                same_lane_training_points=sum(
                    r["rx"] == target[0]["rx"]
                    and (r["channel"] > 4) == (target[0]["channel"] > 4)
                    and not h
                    for r, h in zip(points, held, strict=True)
                ),
                held_uncalibrated_rms_hz=rms(measured[held]),
                held_rms_hz=rms(wrap(measured[held] - X[held] @ coef, FOLD_HZ)),
            )
            predictions[arm][f"L{i}"] = pred.tolist()
    return fits, predictions


class Support:
    def __init__(self, target):
        self.t = np.array([r["time_s"] for r in target])
        self.y = np.array([r["graph_cfo_hz"] for r in target])
        self.q = (self.t - self.t.mean()) / 100
        self.pieces = np.array([r["graph"] for r in target])
        self.names = sorted(set(self.pieces))
        self.folds = [self.pieces == n for n in self.names]
        self.full = np.ones(len(self.t), dtype=bool)
        self._models = {}
        for use in (*self.folds, self.full):
            by = np.unique(self.pieces[use], return_inverse=True)[1]
            X = np.eye(by.max() + 1)[by]
            W = covariance(self.t[use])
            design = W @ X
            self._models[use.tobytes()] = (by, W, design, np.linalg.pinv(design), W @ self.q[use])

    def fit(self, expected, choices, use, rate_allowed):
        by, whitener, design, inv, slope = self._models[use.tobytes()]
        observed = self.y[use]
        d = (observed[None, :] - expected[choices][:, use]) @ whitener.T
        center = np.round((d @ inv.T) / FOLD_HZ)
        cost = np.full(len(choices), np.inf)
        best_alias = np.zeros_like(center)
        best_rate = np.zeros(len(choices))
        for delta in product((-1, 0, 1), repeat=center.shape[1]):
            alias = center + delta
            residual = d - (alias * FOLD_HZ) @ design.T
            if rate_allowed:
                rate = np.clip((residual @ slope) / (slope @ slope + 1 / 1500**2), -6000, 6000)
                residual -= rate[:, None] * slope
            else:
                rate = np.zeros(len(choices))
            objective = (
                np.sum(residual**2, axis=1) + (rate / 1500) ** 2 + (PHASES[choices] / 2.5) ** 2
            )
            better = objective < cost
            best_alias[better], best_rate[better], cost[better] = (
                alias[better],
                rate[better],
                objective[better],
            )
        j = int(np.argmin(cost))
        i = choices[j]
        return dict(
            phase_index=int(i),
            phase_s=float(PHASES[i]),
            alias=best_alias[j].astype(int).tolist(),
            rate_hz_per_100s=float(best_rate[j]),
            normalized_joint=float(cost[j] / use.sum()),
        )

    def residual(self, predicted, parameter):
        y = predicted[parameter["phase_index"]] + parameter["rate_hz_per_100s"] * self.q
        return y, self.y - y


def score_candidate(support, f, radio, visibility, level):
    eligible = np.flatnonzero(visibility >= HORIZON)
    choices = eligible if level in ("L3", "L4r") else eligible[eligible == len(PHASES) // 2]
    if not len(choices):
        return None
    p = f + radio[None, :]
    regression = level == "L4r"
    all_fit = support.fit(p, choices, support.full, regression)
    _, residual = support.residual(p, all_fit)
    lifted = (
        residual
        - np.array([all_fit["alias"][support.names.index(n)] for n in support.pieces]) * FOLD_HZ
    )
    crosses = []
    for use in support.folds:
        model = support.fit(p, choices, use, regression)
        _, observed = support.residual(p, model)
        held = ~use
        held_residual = wrap(observed[held], FOLD_HZ)
        W = support._models[held.tobytes()][1]
        crosses.append(
            dict(
                model,
                trained_graph=support.pieces[use][0],
                held_rms_hz=rms(held_residual),
                held_whitened_loss=float(np.mean((W @ held_residual) ** 2)),
                held_inside_450=int(np.count_nonzero(abs(held_residual) <= ENVELOPE)),
                held_count=int(held.sum()),
            )
        )
    return dict(
        all_fit,
        full_rms_hz=rms(lifted),
        full_inside_450=int(np.count_nonzero(abs(lifted) <= ENVELOPE)),
        full_max_abs_hz=float(max(abs(lifted))),
        mode_count=len(choices),
        min_elevation_deg=float(np.rad2deg(np.arcsin(visibility[all_fit["phase_index"]]))),
        held_loss=float(np.mean([r["held_whitened_loss"] for r in crosses])),
        folds=crosses,
    )


def preparation():
    verify("selection-lock.json", "ledger-lock.json")
    path = OUT / "fit-plan.json"
    if path.exists():
        raise ValueError("fit plan already sealed")
    save_json(
        path,
        dict(
            protocol_sha256=_sha(OUT / "FIT-PROTOCOL.md"),
            candidate_ledger_sha256=_sha(OUT / "ledger-lock.json"),
            selection_sha256=_sha(OUT / "selection-lock.json"),
            search_source_sha256=_sha(Path(__file__)),
            phases_s=PHASES.tolist(),
            levels=LEVELS,
            arms=ARMS,
            per_bank_wall_limit_s=240,
            cpus=[10, 11],
            cross_validation="exhaustive leave-one-whole-Graph-piece-out",
        ),
    )


def search(regime):
    verify("selection-lock.json", "ledger-lock.json")
    plan = read(OUT / "fit-plan.json")
    check(Path(__file__), plan["search_source_sha256"])
    selection = read(OUT / "selection.json")
    bank = json.loads(gzip.decompress((OUT / "orbital-ledgers.json.gz").read_bytes()))
    ledger, causal = bank[regime], bank["causal"]
    target = [dict(r, rx=r["raw_receiver"] + 1) for r in selection["target"]]
    support = Support(target)
    if len(support.names) != 2:
        raise ValueError("the fixed exhaustive cross-check requires exactly two separated pieces")
    P = selection["proof"]
    site = geodetic_to_ecef_km(*P["position"], 0.0)
    up = ecef_to_enu_matrix(*P["position"])[2]
    anchor = P["metadata"]["anchor_utc_ns"]
    rf = target[0]["rf_hz"]
    fits, radios = hardware(selection, causal, target)
    output, rejected, curves = [], [], {}
    owner = str(selection["chosen"]["owner"])
    winners = {}
    called = perf_counter()
    ids = sorted(ledger, key=int)
    for start in range(0, len(ids), 192):
        batch = ids[start : start + 192]
        sats = [Satrec.twoline2rv(*ledger[n]["lines"]) for n in batch]
        d, angles = states(sats, anchor, support.t, PHASES, site, up)
        for j, number in enumerate(batch):
            if (angles[j] < HORIZON).all():
                rejected.append(number)
                continue
            f = -rf * d[j] / LIGHT_KM_S
            for arm in ARMS:
                radio = radios[arm]
                for level in LEVELS:
                    correction = (
                        np.zeros_like(support.t)
                        if level == "L0"
                        else np.array(radio["L1" if level == "L1" else "L2"])
                    )
                    fit = score_candidate(support, f, correction, angles[j], level)
                    label = (arm, level)
                    key = (number, *label)
                    row = dict(norad=int(number), arm=arm, level=level, fit=fit)
                    output.append(row)
                    if fit is not None:
                        winners.setdefault(label, []).append((fit["held_loss"], key))
                        predicted, residual = support.residual(f + correction[None, :], fit)
                        curves[key] = dict(
                            own_prediction=predicted.tolist(),
                            physical=f[fit["phase_index"]].tolist(),
                            residual=wrap(residual, FOLD_HZ).tolist(),
                            phase_curves=f.tolist(),
                        )
    best = {key for rows in winners.values() for _, key in sorted(rows)[:5]}
    report = OUT / f"{regime}-search.json.gz"
    polynomial = []
    for use in support.folds:
        polynomial.append(
            dict(
                graph=support.pieces[use][0],
                alternatives=affine_diagnostic(support.y, support.t, use, ~use),
            )
        )
    permitted = best.union({k for k in curves if k[0] == owner})
    result = dict(
        regime=regime,
        catalogue_count=len(ids),
        rejected=rejected,
        candidate_fits=output,
        curve_predictions=[
            dict(norad=int(k[0]), arm=k[1], level=k[2], **curves[k]) for k in sorted(permitted)
        ],
        roots=dict(
            points=len(target),
            piece_lengths={
                n: int(u.sum()) for n, u in zip(support.names, support.folds, strict=True)
            },
        ),
        polynomial=polynomial,
        hardware=fits,
        radio=radios,
        wall_s=perf_counter() - called,
    )
    write(report, gzip.compress(encoded(result), mtime=0))
    save_json(
        OUT / f"{regime}-search-lock.json",
        dict(files={p.name: _sha(p) for p in (report, OUT / "fit-plan.json")}),
    )
    print(regime, len(ids) - len(rejected), len(output), round(result["wall_s"], 2), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("seal", "causal", "later"))
    mode = cli.parse_args().action
    if mode == "seal":
        preparation()
    else:
        search(mode)
