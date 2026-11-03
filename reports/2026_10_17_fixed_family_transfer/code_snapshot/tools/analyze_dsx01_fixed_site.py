"""Bounded fixed-site DSX01 satellite experiment; no acquisition or geographic fit.

Preparation reads storage through public read-only ports. Analysis uses frozen
local inputs, native-Hz aliases, and one shared affine calibration per RX/band.
All output identities are candidate compatibility, not authenticated emitters.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from compare_dsx01_graph_receivers import PERIOD, ROOT, load_tracks

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.propagation import ElementSetCatalogue, propagate_grid
from leo.sky.sampling import SamplingGrid

LATITUDE = 37.849061591561885
LONGITUDE = -122.48574968092912
REFERENCE_RF = 11.5e9
DRIFT_BOUND_HZ_S = 5.0
DRIFT_SIGMA_HZ_S = 2.0
BASE = ROOT / "reports/2026_10_17_dsx01_consensus_calibration/real"
SOURCES = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/sources.json"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def group(track):
    return 2 * (track["receiver"] - 1) + int(track["channel"] > 4)


def components(source, tracks):
    frozen = json.loads((BASE / source / "trimmed/results.json").read_text())
    ownership = frozen["result"]["ownership"]
    groups = {}
    for track in tracks:
        if track["source_id"] == source:
            groups.setdefault(ownership.get(track["key"], track["key"]), []).append(track)
    result = sorted(groups.items())
    assert len(result) == frozen["result"]["output_tracks"]
    return result, np.array(frozen["calibration"]["beta"])


def ecef_states(catalogue, origin, times):
    utc = origin + np.rint(times * 1e9).astype(np.int64)
    state = propagate_grid(catalogue, SamplingGrid(tuple(map(int, utc)), 0, 1.0))
    jd, fr = julian_day_from_utc_ns(utc)
    p, v = teme_to_ecef(
        state.position_teme_km, state.velocity_teme_km_s, greenwich_mean_sidereal_time_rad(jd, fr)
    )
    return p, v, state.usable


def prepare(output):
    from sgp4.exporter import export_tle

    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader

    tracks, hashes = load_tracks()
    sources = json.loads(SOURCES.read_text())
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    store = FastScanStore("/srv/bulk/leo")
    output.mkdir(parents=True, exist_ok=False)
    for source in sources:
        started = time.monotonic()
        sid = source["source_id"]
        origin = source["first_sample_estimate_utc_ns"]
        payload = Path(source["tracking_input_path"]).read_bytes()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if digest != source["tracking_input_sha256"]:
            raise ValueError("tracking input digest changed")
        document = json.loads(payload)
        inventory = store.source(
            document["source"]["session_id"], document["source"]["input_manifest_sha256"]
        )
        manifest = ShortWindowReader(Path(inventory["segments"][0]["path"])).manifest
        targets = manifest.configuration["targets"]
        nominal = {int(t["channel"]): float(t["rf_center_hz"]) for t in targets}
        own = [t for t in tracks if t["source_id"] == sid]
        corrections = {str(t["channel"]): nominal[t["channel"]] - t["rf_hz"] for t in own}
        # Repeated payloads have identical elements. Keep the newest eligible
        # collection for each digest: identical per-NORAD epoch/tie selection.
        eligible = [
            s
            for s in reader.list_snapshots("space-track")
            if origin - 172800_000_000_000 <= s.collected_utc_ns <= origin
        ]
        unique = {}
        for snapshot in eligible:
            unique[snapshot.sha256] = snapshot

        class UniqueReader:
            def __init__(self, snapshots):
                self.snapshots = snapshots

            def list_snapshots(self, provider):
                return self.snapshots

            def read(self, snapshot):
                return reader.read(snapshot)

        causal = causal_catalogue(UniqueReader(tuple(unique.values())), origin)
        coarse = np.arange(0.0, 306.0, 5.0)
        p, v, usable = ecef_states(causal.catalogue, origin, coarse)
        invalid_coarse_count = int((~usable).sum())
        observer = geodetic_to_ecef_km(LATITUDE, LONGITUDE, 0.0)
        enu = ecef_to_enu_matrix(LATITUDE, LONGITUDE)
        _, elevation, _, _ = look_angles(p, v, observer, enu)
        indexes = np.flatnonzero(usable & (np.max(elevation, axis=1) >= -6.0))
        cat = causal.catalogue
        selected = ElementSetCatalogue(
            tuple(cat.names[i] for i in indexes),
            tuple(cat.satellite_numbers[i] for i in indexes),
            tuple(cat.satellites[i] for i in indexes),
        )
        times = np.unique(np.concatenate([t["times"] for t in own] + [np.arange(0.0, 301.0)]))
        p, v, usable = ecef_states(selected, origin, times)
        if not usable.all():
            raise ValueError("selected candidate has propagation error")
        arrays = {"time_s": times, "norad": np.array(selected.satellite_numbers)}
        for height in (-100, 0, 100):
            observer = geodetic_to_ecef_km(LATITUDE, LONGITUDE, height)
            _, elevation, _, rate = look_angles(p, v, observer, enu)
            arrays[f"doppler_{height}"] = -REFERENCE_RF * rate / 299792.458
            if height == 0:
                arrays["elevation_deg"] = elevation
        dest = output / sid
        dest.mkdir()
        np.savez_compressed(dest / "bank.npz", **arrays)
        # Export only selected elements for exact reproducible future refinement.
        (dest / "selected.tle").write_text(
            "".join(
                f"0 {name}\n{lines[0]}\n{lines[1]}\n"
                for name, sat in zip(selected.names, selected.satellites, strict=True)
                for lines in [export_tle(sat)]
            )
        )
        receipt = dict(
            source_id=sid,
            latitude_deg=LATITUDE,
            longitude_deg=LONGITUDE,
            assumed_altitude_m=0,
            altitude_sensitivity_m=[-100, 100],
            origin_utc_ns=origin,
            tracking_input_sha256=digest,
            nominal_corrections_hz=corrections,
            targets=targets,
            clock_anchor=document["clock_anchor"],
            catalogue_count=len(cat),
            selected_count=len(selected),
            archive_snapshots=len(eligible),
            unique_payloads=len(unique),
            causal_rule="collection and element epoch <= scan start; age <= 48 h",
            provenance=[causal.provenance[i] for i in indexes],
            source_hashes=hashes,
            invalid_coarse_count=invalid_coarse_count,
            numerical_frame="SGP4 TEME; UTC approximates UT1; no polar motion",
            learned_rf_coefficient_c=0,
            preparation_seconds=time.monotonic() - started,
        )
        receipt["bank_sha256"] = hashlib.sha256((dest / "bank.npz").read_bytes()).hexdigest()
        receipt["selected_tle_sha256"] = hashlib.sha256(
            (dest / "selected.tle").read_bytes()
        ).hexdigest()
        write_json(dest / "receipt.json", receipt)
        print(
            json.dumps(
                {
                    k: receipt[k]
                    for k in (
                        "source_id",
                        "catalogue_count",
                        "selected_count",
                        "unique_payloads",
                        "preparation_seconds",
                    )
                }
            ),
            flush=True,
        )


def statistics(groups, bank, corrections, height=0):
    """Exact sufficient statistics; no per-track offset in the fitted model."""
    # npz members decompress on every access. Materialize once for this scan.
    if isinstance(bank, np.lib.npyio.NpzFile):
        bank = {key: bank[key] for key in bank.files}
    fragments, starts, comp_index = [], [], []
    means, cross, centered_rss, visible = [], [], [], []
    ns, mx, xx, gs, qs, curvature, fragment_active = [], [], [], [], [], [], []
    for ci, (_, members) in enumerate(groups):
        starts.append(len(fragments))
        active = False
        for track in members:
            t = track["times"]
            indexes = np.searchsorted(bank["time_s"], t)
            if not np.array_equal(bank["time_s"][indexes], t):
                raise ValueError("bank lacks exact measurement times")
            x = (t - 150) / 150
            xc = x - x.mean()
            q = track["rf_hz"] / REFERENCE_RF
            z = track["values"][None, :] - q * bank[f"doppler_{height}"][:, indexes]
            z -= corrections[str(track["channel"])]
            mean = z.mean(axis=1)
            centered = z - mean[:, None]
            means.append(mean)
            cross.append(centered @ xc)
            centered_rss.append(np.sum(centered**2, axis=1))
            visible.append(np.min(bank["elevation_deg"][:, indexes], axis=1) >= 0.0)
            yd = track["values"] - track["values"].mean()
            affine = yd - xc * (yd @ xc) / max(xc @ xc, 1e-12)
            # Active measured curvature, not merely a degree-2 polynomial label.
            curved = np.ptp(t) >= 20 and np.sqrt(np.mean(affine**2)) >= 250
            active |= curved
            fragment_active.append(curved)
            fragments.append(track)
            comp_index.append(ci)
            ns.append(len(t))
            mx.append(x.mean())
            xx.append(xc @ xc)
            gs.append(group(track))
            qs.append(q)
        curvature.append(active)
    result = dict(
        fragments=fragments,
        starts=np.array(starts),
        ci=np.array(comp_index),
        n=np.array(ns),
        mx=np.array(mx),
        xx=np.array(xx),
        g=np.array(gs),
        q=np.array(qs),
        mean=np.array(means),
        xz=np.array(cross),
        rss=np.array(centered_rss),
        visible=np.array(visible),
        active=np.array(curvature),
        fragment_active=np.array(fragment_active),
    )
    result["count"] = np.add.reduceat(result["n"], result["starts"])
    shape = np.maximum(
        0, result["rss"] - result["xz"] ** 2 / np.maximum(result["xx"][:, None], 1e-12)
    )
    result["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, result["starts"], axis=0) / result["count"][:, None]
    )
    result["component_visible"] = np.logical_and.reduceat(
        result["visible"], result["starts"], axis=0
    )
    return result


def evaluate(stats, beta):
    """Profile only integer native-Hz aliases, never a continuous track intercept."""
    b = beta[stats["g"], None]
    if len(beta) == 9:
        b = b + beta[8] * (stats["q"][:, None] * 11.5 - 11.5)
    d = beta[stats["g"] + 4, None]
    k = np.rint((b + d * stats["mx"][:, None] - stats["mean"]) / PERIOD)
    mean = stats["mean"] + k * PERIOD - b - d * stats["mx"][:, None]
    rss = (
        stats["n"][:, None] * mean**2
        + stats["rss"]
        - 2 * d * stats["xz"]
        + d * d * stats["xx"][:, None]
    )
    rss = np.add.reduceat(np.maximum(rss, 0), stats["starts"], axis=0)
    mse = rss / stats["count"][:, None]
    mse[~stats["component_visible"]] = 1e30
    best = np.argmin(mse, axis=1)
    rms = np.sqrt(mse[np.arange(len(best)), best])
    return best, rms, k, mse


def fit_shared(stats, best, rms, k, beta, gate):
    """Only actively curved components calibrate. Linear components never vote."""
    new = beta.copy()
    ci = stats["ci"]
    keep = stats["active"][ci] & stats["fragment_active"] & (rms[ci] < gate)
    selected = best[ci]
    z = stats["mean"][np.arange(len(ci)), selected]
    z += k[np.arange(len(ci)), selected] * PERIOD
    xz = stats["xz"][np.arange(len(ci)), selected]
    # Each component has at most 50 effective votes, independent of point density.
    w = np.minimum(1.0, 50 / stats["count"][ci])
    ranks = []
    bound = 150 * DRIFT_BOUND_HZ_S
    prior_precision = 150.0**2 / (150 * DRIFT_SIGMA_HZ_S) ** 2
    if len(beta) == 9:
        features = np.zeros((len(ci), 9))
        features[np.arange(len(ci)), stats["g"]] = 1.0
        features[np.arange(len(ci)), stats["g"] + 4] = stats["mx"]
        features[:, 8] = stats["q"] * 11.5 - 11.5
        weight = w * stats["n"] * keep
        design = features.T @ (features * weight[:, None])
        rhs = features.T @ (weight * z)
        for g in range(4):
            m = keep & (stats["g"] == g)
            design[g + 4, g + 4] += sum(w[m] * stats["xx"][m])
            if np.any(m):
                design[g + 4, g + 4] += prior_precision
            rhs[g + 4] += sum(w[m] * xz[m])
        delta = np.linalg.lstsq(design, rhs - design @ beta, rcond=1e-10)[0]
        new += delta
        new[8] = np.clip(new[8], -200000.0, 200000.0)
        new[4:8] = np.clip(new[4:8], -bound, bound)
        # Update aliases only in evaluate; the continuous solve has no per-track
        # intercept. Refit shared intercepts after imposing bounds.
        for g in range(4):
            m = keep & (stats["g"] == g)
            xx = stats["xx"][m]
            n, x, weight = stats["n"][m], stats["mx"][m], w[m]
            normal = np.array(
                [
                    [sum(weight * n), sum(weight * n * x)],
                    [sum(weight * n * x), sum(weight * (xx + n * x * x))],
                ]
            )
            ranks.append(int(np.linalg.matrix_rank(normal)))
            if sum(weight * n):
                h = stats["q"][m] * 11.5 - 11.5
                new[g] = sum(weight * n * (z[m] - new[g + 4] * x - new[8] * h)) / sum(weight * n)
                new[g] = (new[g] + PERIOD / 2) % PERIOD - PERIOD / 2
        return new, ranks
    for g in range(4):
        m = keep & (stats["g"] == g)
        n, x, sx, weight = stats["n"][m], stats["mx"][m], stats["xx"][m], w[m]
        design = np.array(
            [
                [sum(weight * n), sum(weight * n * x)],
                [sum(weight * n * x), sum(weight * (sx + n * x * x))],
            ]
        )
        rank = int(np.linalg.matrix_rank(design))
        ranks.append(rank)
        if rank == 2:
            design[1, 1] += prior_precision
            rhs = np.array([sum(weight * n * z[m]), sum(weight * (xz[m] + n * x * z[m]))])
            value = np.linalg.solve(design, rhs)
            new[g + 4] = np.clip(value[1], -bound, bound)
            # Refit intercept after enforcing the declared physical drift bound.
            new[g] = sum(weight * n * (z[m] - new[g + 4] * x)) / sum(weight * n)
            new[g] = (new[g] + PERIOD / 2) % PERIOD - PERIOD / 2
    return new, ranks


def seed_calibrations(stats, beta, budget=160):
    beta = beta.copy()
    bound = 150 * DRIFT_BOUND_HZ_S
    beta[4:8] = np.clip(beta[4:8], -bound, bound)
    yield beta.copy()
    anchors = np.flatnonzero(stats["active"])
    anchors = sorted(anchors, key=lambda c: -stats["count"][c])[:20]
    qgroup = np.array(
        [np.mean(stats["q"][stats["g"] == g]) if np.any(stats["g"] == g) else 1.0 for g in range(4)]
    )
    emitted = 0
    for ci in anchors:
        rows = np.flatnonzero((stats["ci"] == ci) & stats["fragment_active"])
        # Curvature alone can rank an impossible Doppler slope ahead of the
        # correct object. Bound seed slopes, allowing 450 Hz over a short span.
        slopes = stats["xz"][rows] / np.maximum(stats["xx"][rows, None], 1e-12)
        spans = np.array([np.ptp(stats["fragments"][r]["times"]) for r in rows])
        limits = bound + 450 * 150 / np.maximum(spans, 1.0)
        possible = np.all(np.abs(slopes) <= limits[:, None], axis=0)
        order = np.argsort(
            np.where(stats["component_visible"][ci] & possible, stats["shape_rms"][ci], np.inf)
        )[:8]
        for satellite in order:
            if not stats["component_visible"][ci, satellite] or not possible[satellite]:
                continue
            # A discovery gauge seed only. Final model is eight shared native-Hz
            # parameters, and final RMS never removes a free track affine term.
            row = rows[np.argmax(stats["n"][rows])]
            g = stats["g"][row]
            slope = stats["xz"][row, satellite] / max(stats["xx"][row], 1e-12)
            intercept = stats["mean"][row, satellite] - slope * stats["mx"][row]
            intercept = (intercept + PERIOD / 2) % PERIOD - PERIOD / 2
            a = (intercept - beta[g]) / stats["q"][row]
            d = (slope - beta[g + 4]) / stats["q"][row]
            seed = beta.copy()
            seed[:4] += a * qgroup
            seed[4:8] = np.clip(seed[4:8] + d * qgroup, -bound, bound)
            for r in rows:
                rg = stats["g"][r]
                rd = stats["xz"][r, satellite] / max(stats["xx"][r], 1e-12)
                seed[rg + 4] = np.clip(rd, -bound, bound)
                seed[rg] = stats["mean"][r, satellite] - seed[rg + 4] * stats["mx"][r]
            seed[:4] = (seed[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
            yield seed
            emitted += 1
            if emitted >= budget:
                return


def solve(stats, initial, budget=160):
    winner = None
    for seed in seed_calibrations(stats, initial, budget):
        beta = seed
        for gate in (4000.0, 2000.0, 1000.0, 600.0, 450.0):
            for _ in range(3):
                best, rms, k, _ = evaluate(stats, beta)
                new, ranks = fit_shared(stats, best, rms, k, beta, gate)
                delta = np.max(np.abs(new - beta))
                beta = new
                if delta < 0.01:
                    break
        best, rms, _, _ = evaluate(stats, beta)
        # Robust in-sample discovery objective, capped per curved component.
        active = stats["active"]
        score = np.sum(
            np.minimum(stats["count"][active], 50) * np.minimum(rms[active] ** 2, 900.0**2)
        )
        score += 150.0**2 * np.sum((beta[4:8] / (150 * DRIFT_SIGMA_HZ_S)) ** 2)
        if winner is None or score < winner[0]:
            winner = (score, beta.copy(), ranks)
    return winner[1], winner[2]


def residual_diagnostics(residual, times):
    residual, times = np.asarray(residual), np.asarray(times)
    x = times - times.mean()
    slope = float(residual @ x / max(x @ x, 1e-12))
    ordered = residual[np.argsort(times)]
    half = len(ordered) // 2
    step = abs(float(ordered[:half].mean() - ordered[half:].mean())) if half else 0.0
    return dict(
        mean_hz=float(residual.mean()),
        rms_hz=float(np.sqrt(np.mean(residual**2))),
        slope_hz_s=slope,
        trend_excursion_hz=abs(slope) * float(np.ptp(times)),
        half_difference_hz=step,
        max_abs_hz=float(np.max(np.abs(residual))),
    )


def noise_screen(residual, times):
    """Conservative structure checks, not a physical-ID probability."""
    order = np.argsort(times)
    r, t = np.asarray(residual)[order], np.asarray(times)[order]
    n = len(r)
    x = t - t.mean()
    sigma = max(float(np.std(r, ddof=1)), 75.0)
    mean_z = abs(float(r.mean())) * np.sqrt(n) / sigma
    slope_z = abs(float(r @ x)) / max(sigma * np.sqrt(x @ x), 1e-12)
    tx = x / max(float(np.ptp(t)) / 2, 1.0)
    design = np.stack([np.ones(n), tx, tx * tx], axis=1)
    fitted = design @ np.linalg.lstsq(design, r, rcond=None)[0]
    rss0 = max(float(r @ r), n * 75.0**2)
    rss1 = max(float((r - fitted) @ (r - fitted)), n * 75.0**2)
    bic_gain = n * np.log(rss0 / rss1) - 3 * np.log(n)
    step_z = max(
        [
            abs(float(r[:j].mean() - r[j:].mean())) / (sigma * np.sqrt(1 / j + 1 / (n - j)))
            for j in range(4, n - 3)
        ]
        or [0.0]
    )
    centered = r - r.mean()
    acf = float(centered[:-1] @ centered[1:] / max(centered @ centered, 1e-12))
    passed = mean_z <= 3 and slope_z <= 3 and bic_gain <= 10 and step_z <= 4
    passed &= abs(acf) <= 4 / np.sqrt(n)
    return dict(
        noise_screen_pass=bool(passed),
        mean_z=float(mean_z),
        slope_z=float(slope_z),
        quadratic_bic_gain=float(bic_gain),
        maximum_step_z=float(step_z),
        lag1_acf=acf,
    )


def run(inputs, output, budget, fit_rf_c=False, null_seed=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tracks, hashes = load_tracks()
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for sid in ("S01", "S02", "S03", "S04", "S05"):
        started = time.monotonic()
        bankpath = inputs / sid / "bank.npz"
        receipt = json.loads((inputs / sid / "receipt.json").read_text())
        if receipt["bank_sha256"] != hashlib.sha256(bankpath.read_bytes()).hexdigest():
            raise ValueError("orbit bank digest changed")
        if receipt["source_hashes"] != hashes:
            raise ValueError("Graph observations changed")
        with np.load(bankpath) as archive:
            bank = {key: archive[key] for key in archive.files}
        groups, initial = components(sid, tracks)
        if null_seed is not None:
            rng = np.random.default_rng(null_seed + int(sid[1:]))
            transformed = []
            for key, members in groups:
                delta = rng.uniform(-PERIOD / 2, PERIOD / 2)
                transformed.append(
                    (
                        key,
                        [
                            dict(
                                track,
                                values=track["values"] + track["rf_hz"] / REFERENCE_RF * delta,
                            )
                            for track in members
                        ],
                    )
                )
            groups = transformed
        if fit_rf_c:
            initial = np.r_[initial, 0.0]
        stats = statistics(groups, bank, receipt["nominal_corrections_hz"])
        beta, ranks = solve(stats, initial, budget)
        best, rms, lifts, mse = evaluate(stats, beta)
        rows = []
        fig, axes = plt.subplots(3, 1, figsize=(15, 13), constrained_layout=True)
        for ci, (key, members) in enumerate(groups):
            sat = int(best[ci])
            selected_rows = np.flatnonzero(stats["ci"] == ci)
            residuals, times, lane_diags, noise_diags = [], [], [], []
            draw = []
            for fi, track in zip(selected_rows, members, strict=True):
                t = track["times"]
                ix = np.searchsorted(bank["time_s"], t)
                g, q = group(track), track["rf_hz"] / REFERENCE_RF
                alias = int(lifts[fi, sat])
                cal = beta[g] + beta[g + 4] * (t - 150) / 150
                if fit_rf_c:
                    cal = cal + beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                observed = (
                    track["values"]
                    + alias * PERIOD
                    - cal
                    - receipt["nominal_corrections_hz"][str(track["channel"])]
                )
                predicted = q * bank["doppler_0"][sat, ix]
                residual = observed - predicted
                residuals.extend(residual)
                times.extend(t)
                lane_diags.append(residual_diagnostics(residual, t))
                noise_diags.append(noise_screen(residual, t))
                draw.append((t, observed / q, predicted / q))
            diag = residual_diagnostics(residuals, times)
            # These are practical compatibility tolerances, not a calibrated
            # whiteness test or proof of physical identity.
            compatible = bool(stats["component_visible"][ci, sat]) and all(
                d["rms_hz"] <= 450
                and abs(d["mean_hz"]) <= 150
                and d["trend_excursion_hz"] <= 300
                and d["half_difference_hz"] <= 300
                and d["max_abs_hz"] <= 1500
                for d in lane_diags
            )
            alternatives = np.argsort(mse[ci])[:2]
            second_rms = float(np.sqrt(mse[ci, alternatives[1]]))
            separated = compatible and second_rms >= max(600.0, 2 * rms[ci])
            status = (
                "separated_candidate"
                if separated
                else "ambiguous_candidate"
                if compatible
                else "unexplained"
            )
            row = dict(
                source_id=sid,
                component=key,
                fragments=len(members),
                points=len(times),
                active_curvature=bool(stats["active"][ci]),
                candidate_norad=int(bank["norad"][sat]),
                status=status,
                noise_screen_pass=all(d["noise_screen_pass"] for d in noise_diags),
                maximum_mean_z=max(d["mean_z"] for d in noise_diags),
                maximum_slope_z=max(d["slope_z"] for d in noise_diags),
                maximum_quadratic_bic_gain=max(d["quadratic_bic_gain"] for d in noise_diags),
                maximum_step_z=max(d["maximum_step_z"] for d in noise_diags),
                second_rms_hz=second_rms,
                **diag,
            )
            rows.append(row)
            color = plt.get_cmap("tab20")(sat % 20)
            for t, observed, predicted in draw:
                axis = axes[0] if compatible else axes[1]
                axis.scatter(
                    t, observed / 1e3, s=5, color=color if compatible else ".5", alpha=0.65
                )
                if compatible:
                    order = np.argsort(t)
                    axes[0].plot(t[order], predicted[order] / 1e3, color=color, lw=1, alpha=0.75)
            if compatible:
                axes[2].scatter(times, residuals, s=5, color=color, alpha=0.5)
        for ax in axes:
            ax.set_xlabel("Seconds from scan start (UTC anchor in receipt)")
            ax.grid(alpha=0.25)
        axes[0].set(
            title=f"{sid}: satellite-compatible candidates at supplied fixed GPS; curves = SGP4",
            ylabel="Corrected CFO at 11.5 GHz (kHz)",
        )
        axes[1].set(
            title="Unexplained components under the selected shared calibration",
            ylabel="Corrected CFO (kHz)",
        )
        axes[2].set(title="Native-Hz residuals of compatible candidates", ylabel="Residual (Hz)")
        axes[2].axhline(0, color="k", lw=0.8)
        fig.savefig(output / f"{sid}_candidates.png", dpi=150)
        plt.close(fig)
        # Fixed labels/calibration: isolates geometric sensitivity, not a rerun.
        sensitivity = {}
        for height in (-100, 100):
            delta = np.abs(bank[f"doppler_{height}"] - bank["doppler_0"])
            sensitivity[str(height)] = float(np.max(delta))
        support = []
        for g in range(4):
            cc = sorted(
                set(
                    stats["ci"][
                        (stats["g"] == g) & stats["fragment_active"] & (rms[stats["ci"]] < 450)
                    ]
                )
            )
            qualified = [
                ci
                for ci in cc
                if rows[ci]["status"] == "separated_candidate" and rows[ci]["noise_screen_pass"]
            ]
            numbers = {int(best[ci]) for ci in qualified}
            evidence_times = [
                t["times"] for ci in qualified for t in groups[ci][1] if group(t) == g
            ]
            time_span = float(np.ptp(np.concatenate(evidence_times))) if evidence_times else 0.0
            bound_active = abs(beta[g + 4] / 150) >= DRIFT_BOUND_HZ_S - 0.001
            support.append(
                dict(
                    group=g,
                    curved_components=len(cc),
                    norads=len(set(map(int, best[cc]))),
                    provisional_overdetermined=len(cc) >= 3 and len(set(best[cc])) >= 2,
                    qualified_curved_components=len(qualified),
                    qualified_norads=len(numbers),
                    qualified_time_span_s=time_span,
                    drift_bound_active=bool(bound_active),
                    calibration_screen_pass=(
                        len(qualified) >= 3
                        and len(numbers) >= 2
                        and time_span >= 30
                        and not bound_active
                    ),
                )
            )
        for ci, row in enumerate(rows):
            paths = {group(t) for t in groups[ci][1]}
            row["calibration_screen_pass"] = all(
                support[g]["calibration_screen_pass"] for g in paths
            )
            row["evidence_screen_pass"] = (
                row["calibration_screen_pass"]
                and row["noise_screen_pass"]
                and row["status"] == "separated_candidate"
            )
        summary = dict(
            source_id=sid,
            components=len(groups),
            points=int(sum(stats["count"])),
            active_curvature_components=int(sum(stats["active"])),
            compatible_components=sum(r["status"] != "unexplained" for r in rows),
            compatible_points=sum(r["points"] for r in rows if r["status"] != "unexplained"),
            separated_components=sum(r["status"] == "separated_candidate" for r in rows),
            separated_points=sum(r["points"] for r in rows if r["status"] == "separated_candidate"),
            noise_screened_components=sum(
                r["status"] != "unexplained" and r["noise_screen_pass"] for r in rows
            ),
            noise_screened_points=sum(
                r["points"] for r in rows if r["status"] != "unexplained" and r["noise_screen_pass"]
            ),
            evidence_screened_components=sum(r["evidence_screen_pass"] for r in rows),
            evidence_screened_points=sum(r["points"] for r in rows if r["evidence_screen_pass"]),
            null_seed=null_seed,
            candidate_norads=sorted(
                {r["candidate_norad"] for r in rows if r["status"] != "unexplained"}
            ),
            beta_native_hz_and_hz_per_150s=beta.tolist(),
            learned_rf_c_hz_per_ghz=float(beta[8]) if fit_rf_c else 0.0,
            learned_rf_c_dimensionless=float(beta[8]) / 1e9 if fit_rf_c else 0.0,
            seed_budget=budget,
            drift_bound_hz_s=DRIFT_BOUND_HZ_S,
            drift_prior_sigma_hz_s=DRIFT_SIGMA_HZ_S,
            calibration_group_ranks=ranks,
            calibration_support=support,
            height_max_reference_doppler_change_hz=sensitivity,
            elapsed_s=time.monotonic() - started,
        )
        summaries.append(summary)
        with (output / f"{sid}_components.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        write_json(
            output / f"{sid}_results.json", dict(summary=summary, components=rows, receipt=receipt)
        )
        print(json.dumps(summary), flush=True)
    write_json(output / "summary.json", summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-budget", type=int, default=160)
    parser.add_argument("--fit-rf-c", action="store_true")
    parser.add_argument("--null-seed", type=int)
    parser.add_argument("--drift-bound-hz-s", type=float, default=DRIFT_BOUND_HZ_S)
    parser.add_argument("--drift-sigma-hz-s", type=float, default=DRIFT_SIGMA_HZ_S)
    args = parser.parse_args()
    if args.drift_bound_hz_s <= 0 or args.drift_sigma_hz_s <= 0 or args.seed_budget < 1:
        parser.error("positive drift bounds, prior sigma, and seed budget required")
    DRIFT_BOUND_HZ_S = args.drift_bound_hz_s
    DRIFT_SIGMA_HZ_S = args.drift_sigma_hz_s
    if Path("/mnt/qnap01") in args.output.resolve().parents:
        parser.error("QNAP is read-only")
    if args.action == "prepare":
        prepare(args.output)
    else:
        run(args.inputs, args.output, args.seed_budget, args.fit_rf_c, args.null_seed)
