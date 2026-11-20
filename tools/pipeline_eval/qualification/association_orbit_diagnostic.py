"""Causal and later harmonic-aware Doppler checks on two preselected Graph curves."""

import gzip
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy.linalg import cholesky, solve_triangular
from sgp4.alpha5 import from_alpha5
from sgp4.api import Satrec, SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)

from ..__main__ import save_json
from ..variants import robust_em as lean
from . import association_evidence as audit
from . import native_joint_trial as trial
from .phase_confirmation import frozen_inputs

STORE = Path("/mnt/qnap01/mouse9911/tle")
C = 299792.458
LEVELS = ("L0", "L1", "L2", "L3", "L4r")
PHASE_GRID = np.linspace(-7.5, 7.5, 13)
NS = 10**9


def digest(raw):
    return sha256(raw).hexdigest()


def elements(raw, collected, source):
    lines = raw.decode("ascii").splitlines()
    for name, first, second in zip(lines[::3], lines[1::3], lines[2::3], strict=True):
        year = int(first[18:20])
        date = datetime(2000 + year if year < 57 else 1900 + year, 1, 1, tzinfo=UTC)
        epoch = int((date + timedelta(days=float(first[20:32]) - 1)).timestamp() * NS)
        if first[2:7] != second[2:7]:
            raise ValueError("TLE pair identity mismatch")
        yield (
            from_alpha5(first[2:7]),
            dict(
                name=name,
                epoch_ns=epoch,
                collected_ns=collected,
                source=source,
                sha256=digest((first + "\n" + second + "\n").encode()),
                lines=[first, second],
            ),
        )


def banks(path, document):
    cutoff = document["cutoff_utc_ns"]
    collected = document["catalog_timestamp_ns"]
    end = document["anchor_utc_ns"] + int(NS * document["duration_s"])
    causal = {}
    for number, record in elements(path.read_bytes(), collected, path.name):
        if cutoff - 48 * 3600 * NS <= record["epoch_ns"] <= collected <= cutoff and (
            number not in causal or record["epoch_ns"] > causal[number]["epoch_ns"]
        ):
            causal[number] = record
    later, used, snapshots = {}, set(), []
    now = datetime.fromtimestamp(end / NS, UTC)
    for offset in range(3):
        date = now + timedelta(days=offset)
        folder = STORE / "snapshots/space-track/starlink" / date.strftime("%Y/%m/%d")
        for path in sorted(folder.glob("*.json")):
            meta = json.loads(path.read_bytes())
            grabbed = int(datetime.fromisoformat(meta["retrieved_at"]).timestamp() * NS)
            token = meta["raw_sha256"]
            if not end < grabbed <= end + 48 * 3600 * NS or token in used:
                continue
            raw = (STORE / meta["raw_object"]).read_bytes()
            if digest(raw) != token:
                raise ValueError("later snapshot bytes differ from their receipt")
            used.add(token)
            snapshots.append(dict(collected_ns=grabbed, sha256=token, snapshot=meta["snapshot"]))
            for number, row in elements(raw, grabbed, token):
                if end < row["epoch_ns"] <= end + 48 * 3600 * NS and (
                    number not in later
                    or (row["epoch_ns"], grabbed)
                    < (later[number]["epoch_ns"], later[number]["collected_ns"])
                ):
                    later[number] = row
    return {"causal": causal, "later": later}, snapshots


def covariance(t):
    cov = lean.CORRELATED_HZ**2 * np.exp(-abs(t[:, None] - t) / lean.CORRELATION_S)
    cov.flat[:: len(t) + 1] += lean.WHITE_HZ**2
    return solve_triangular(cholesky(cov, lower=True), np.eye(len(t)), lower=True)


def blocks(t):
    group = np.floor(t / 8).astype(int)
    rng = np.random.default_rng(20261119)
    unique = rng.permutation(np.unique(group))
    held = np.isin(group, unique[: max(1, len(unique) // 3)])
    keep = ~held & (np.min(abs(t[:, None] - t[held]), axis=1) > lean.CORRELATION_S)
    if min(held.sum(), keep.sum()) < 5:
        raise ValueError("curve has inadequate grouped validation")
    return keep, held, group


def frequencies(satellites, anchor, t, site, frame, rf):
    jd, fraction = julian_day_from_utc_ns(anchor + np.rint(t * NS).astype("int64"))
    error, p, v = SatrecArray(satellites).sgp4(jd, fraction)
    p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fraction))
    d = p - site
    with np.errstate(invalid="ignore", divide="ignore"):
        length = np.linalg.norm(d, axis=-1)
        ray = d / length[..., None]
        radial = (ray * v).sum(axis=-1)
        doppler = -rf / C * radial
        up = ray @ frame[2]
        gradients = (rf / C * (v - ray * radial[..., None]) / length[..., None]) @ frame[:2].T
    valid = (error == 0).all(axis=1) & np.isfinite(doppler).all(axis=1)
    return doppler, up, gradients, valid


def rms(x):
    return float(np.sqrt(np.mean(x * x)))


def affine_diagnostic(y, t, train, held):
    u = (t - t.mean()) / max(np.ptp(t), 1)
    w = covariance(t[train])
    out = []
    for degree in range(5):
        basis = np.polynomial.polynomial.polyvander(u, degree)
        coef = np.linalg.lstsq(w @ basis[train], w @ y[train], rcond=None)[0]
        fit = basis @ coef
        residual = y - fit
        full = np.linalg.lstsq(basis, y, rcond=None)[0]
        leave = np.linalg.lstsq(basis[1:-1], y[1:-1], rcond=None)[0]
        out.append(
            dict(
                degree=degree,
                train_whitened_bic=float(
                    np.sum((w @ residual[train]) ** 2) + (degree + 1) * np.log(train.sum())
                ),
                full_rms_hz=rms(residual),
                held_rms_hz=rms(residual[held]),
                polynomial_hz=fit.tolist(),
                endpoint_leave_both_hz=(basis[[0, -1]] @ (full - leave)).tolist(),
            )
        )
    return out


def fit_case(case):
    path = audit.OUTPUT / f"{case}-native-trace.json.gz"
    trace = json.loads(gzip.decompress(path.read_bytes()))
    observation = trace["trace"]["observation"]
    target = trace["selected"]
    anchor = observation["anchor_utc_ns"]
    track = observation["tracks"][target["index"]]
    coords = trace["result"]["arms"]["c0"]["forced_latlon"]
    site, frame = geodetic_to_ecef_km(*coords, 0), ecef_to_enu_matrix(*coords)
    t, y = (np.asarray(track[k]) for k in ("times", "values"))
    rf = track["rf_hz"]
    train, held, group = blocks(t)
    w = covariance(t[train])
    v = covariance(t[held])
    q = (t - observation["duration_s"] / 2) / 100
    elements_by_time, snapshots = banks(
        trial.native.request(frozen_inputs()[case], "native")[1]["catalogue"], observation
    )
    prior = trace["trace"]["banks"][1]
    lane = target["lane"]
    track_by_index = {r["index"]: r for r in trace["track_inventory"]}
    all_fits, screens, selected = [], {}, {}

    def radio(t2, rf2, state):
        u = (t2 - observation["duration_s"] / 2) / 100
        return (
            state["bias"][lane]
            + state["drift"][lane] * u
            + state["c_hz_per_ghz"] * (rf2 / 1e9 - 11.5)
        )

    def phase_for(number, state):
        return state["phase"][prior.index(number)] if number in prior else 0.0

    causal = elements_by_time["causal"]
    independent = []
    anchor_ids = set((target["joint_train"], target["joint_pool"], *map(int, target["v5_c0"]))) - {
        None
    }
    state0 = trace["trace"]["fit_states"]["c0"]
    for k, row in track_by_index.items():
        number = row["joint_pool"]
        if (
            k == target["index"]
            or number in anchor_ids
            or row["lane"] != lane
            or number not in causal
            or row["v5_c0"].get(str(number), 0) < row["unique_points"] // 2
        ):
            continue
        arc = observation["tracks"][k]
        t2, y2 = (np.asarray(arc[v]) for v in ("times", "values"))
        signal = frequencies(
            [Satrec.twoline2rv(*causal[number]["lines"])],
            anchor,
            t2 + phase_for(number, state0),
            site,
            frame,
            arc["rf_hz"],
        )[0][0]
        residual = (
            y2 - row["pooled"]["alias"] * lean.PERIOD - signal - radio(t2, arc["rf_hz"], state0)
        )
        if np.isfinite(residual).all():
            independent.append(
                dict(
                    norad=number,
                    track=k,
                    time_s=float(t2.mean()),
                    residual_hz=float(np.median(residual)),
                )
            )
    training_refs = [r for r in independent if digest(str(r["norad"]).encode())[-1] not in "0123"]
    held_refs = [r for r in independent if r not in training_refs]
    x = np.array([(r["time_s"] - observation["duration_s"] / 2) / 100 for r in training_refs])
    external = np.array([r["residual_hz"] for r in training_refs])
    clock = (
        np.linalg.lstsq(np.column_stack((np.ones(len(x)), x)), external, rcond=None)[0]
        if len({r["norad"] for r in training_refs}) >= 3
        else None
    )
    correction = np.zeros(2) if clock is None else clock
    clock_lines = {
        "L0": np.zeros(len(t)),
        "L1": np.full(len(t), correction[0]),
        "L2": correction[0] + correction[1] * q,
    }
    for regime, book in elements_by_time.items():
        norms, considered = {}, 0
        ids = sorted(book)
        bank = [Satrec.twoline2rv(*book[number]["lines"]) for number in ids]
        for start in range(0, len(ids), 192):
            order = ids[start : start + 192]
            f, up, _, valid = frequencies(bank[start : start + 192], anchor, t, site, frame, rf)
            usable = np.flatnonzero(valid & (up >= -0.035).all(axis=1))
            considered += len(usable)
            rr = (y - f[usable] - radio(t, rf, state0))[..., train] @ w.T
            one = w.sum(axis=1)
            drift = w @ q[train]
            g = np.linalg.qr(np.column_stack((one, drift)))[0]
            affine = rr - (rr @ g) @ g.T
            baseline = (
                rr - np.rint((rr @ one) / (lean.PERIOD * (one @ one)))[:, None] * lean.PERIOD * one
            )
            for i, a, b in zip(
                usable, np.sum(affine**2, axis=1), np.sum(baseline**2, axis=1), strict=True
            ):
                norms[order[i]] = [float(a), float(b)]
        screens[regime] = dict(
            catalogue=len(book),
            physically_visible=considered,
            leaders_affine=sorted(norms, key=lambda k: norms[k][0])[:8],
            leaders_frozen=sorted(norms, key=lambda k: norms[k][1])[:8],
        )
        selected[regime] = norms
    finalists = set.union(
        anchor_ids, *(set(s["leaders_affine"] + s["leaders_frozen"]) for s in screens.values())
    )
    for regime, book in elements_by_time.items():
        for number in sorted(finalists):
            if number not in selected[regime]:
                continue
            sat = Satrec.twoline2rv(*book[number]["lines"])
            for arm, state in trace["trace"]["fit_states"].items():
                radio0 = radio(t, rf, state)
                saved = phase_for(number, state)
                phase_choices = np.unique(np.r_[PHASE_GRID, saved])
                orbit = {}
                for p in phase_choices:
                    f, up, grad, valid = frequencies([sat], anchor, t + p, site, frame, rf)
                    if valid[0] and (up >= -0.035).all():
                        orbit[p] = (f[0], up[0], grad[0])
                for level in LEVELS:
                    available = [saved] if level in clock_lines else orbit.keys()
                    possibilities = []
                    for p in available:
                        if p not in orbit:
                            continue
                        f, up, grad = orbit[p]
                        delta = y - f - radio0 - clock_lines.get(level, clock_lines["L2"])
                        one = w.sum(axis=1)
                        alias = round(((w @ delta[train]) @ one) / (lean.PERIOD * (one @ one)))
                        for branch in range(alias - 1, alias + 2):
                            residual = delta - branch * lean.PERIOD
                            rate = 0.0
                            penalty = (p / 2.5) ** 2 if level not in clock_lines else 0
                            if level == "L4r":
                                d = w @ q[train]
                                rate = np.clip(
                                    d @ (w @ residual[train]) / (d @ d + 1 / 1500**2), -6000, 6000
                                )
                                residual = residual - rate * q
                                penalty += (rate / 1500) ** 2
                            loss = float(np.sum((w @ residual[train]) ** 2) + penalty)
                            possibilities.append((loss, p, branch, rate, residual, f, grad))
                    if not possibilities:
                        continue
                    loss, p, branch, rate, residual, f, grad = min(
                        possibilities, key=lambda x: x[0]
                    )
                    z = covariance(t)
                    derivative = np.gradient(f, t)
                    nuisance = z @ np.column_stack((np.ones(len(t)), q, derivative))
                    design = z @ grad
                    projected = design - nuisance @ np.linalg.lstsq(nuisance, design, rcond=None)[0]
                    _, singular, axes = np.linalg.svd(projected, full_matrices=False)
                    all_fits.append(
                        dict(
                            norad=number,
                            regime=regime,
                            arm=arm,
                            level=level,
                            element=book[number],
                            training_loss=loss / train.sum(),
                            held_whitened_loss=float(np.mean((v @ residual[held]) ** 2)),
                            full_rms_hz=rms(residual),
                            held_rms_hz=rms(residual[held]),
                            phase_s=float(p),
                            alias=branch,
                            orbit_rate_hz_per_100s=float(rate),
                            singular_values_per_km=singular.tolist(),
                            weak_axis_en=axes[-1].tolist(),
                            phase_drift_correlation=float(np.corrcoef(derivative, q)[0, 1]),
                            residual_hz=residual.tolist(),
                            physical_hz=f.tolist(),
                            adjusted_hz=(y - residual).tolist(),
                        )
                    )
    return dict(
        case=case,
        observation_sha256=trace["observation_sha256"],
        t=t.tolist(),
        y=y.tolist(),
        train=train.tolist(),
        held=held.tolist(),
        blocks=group.tolist(),
        target=target,
        fit_site=coords,
        audits=affine_diagnostic(y, t, train, held),
        catalogue_screens=screens,
        snapshots=snapshots,
        fits=all_fits,
        independent_clock_tracks=independent,
        held_clock_tracks=held_refs,
        receiver_offset_drift_hz=clock.tolist() if clock is not None else None,
    )


def main():
    with ProcessPoolExecutor(2) as pool:
        for row in pool.map(fit_case, audit.CASES):
            save_json(audit.OUTPUT / f"{row['case']}-candidate-fits.json", row)
            print(row["case"], len(row["fits"]), row["catalogue_screens"], flush=True)


if __name__ == "__main__":
    main()
