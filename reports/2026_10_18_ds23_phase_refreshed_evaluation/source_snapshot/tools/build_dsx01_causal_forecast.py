"""Past-only TLE innovation forecasting; no CFO or receiver location is read."""

import json

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from compare_dsx01_retention_localization import ROOT
from sgp4.api import Satrec

from leo.analysis.research.orbit_phase_geometry import (
    EARTH_ROTATION_RAD_S,
    phase_shifted_states,
)
from leo.sky.propagation import ElementSetCatalogue

OUTPUT = ROOT / "reports/2026_10_18_dsx01_causal_repairs"


def causal_history(case):
    """Export a separate past-only input, checking epoch and collection cutoffs."""
    path = ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "causal_history.json"
    source = json.loads(path.read_text())
    data = dict(
        cutoff_utc_ns=source["cutoff_utc_ns"],
        origin_utc_ns=source["origin_utc_ns"],
        candidates={
            n: dict(latest_causal=max(rows, key=lambda r: r["epoch"]), past_versions=rows)
            for n, rows in source["past_versions"].items() if rows
        },
    )
    validate_history(data)
    return data


def validate_history(data):
    cut = data["cutoff_utc_ns"]
    for row in data["candidates"].values():
        if set(row) != {"latest_causal", "past_versions"}:
            raise ValueError("forecast accepts past-only records")
        if row["latest_causal"]["epoch"] > cut:
            raise ValueError("future element epoch")
        for record in row["past_versions"]:
            if record["epoch"] > cut or record["collected_utc_ns"] > cut:
                raise ValueError("noncausal archive record")


def propagate(record, origin, times):
    sat = Satrec.twoline2rv(*record["lines"])
    cat = ElementSetCatalogue((str(sat.satnum),), (sat.satnum,), (sat,))
    p, v, good = ecef_states(cat, origin, np.asarray(times))
    if not good.all():
        raise ValueError("causal forecast propagation failed")
    return dict(time_s=np.asarray(times), position_km=p, velocity_km_s=v)


def innovation(new, old, origin, times):
    """Newest minus phase-aligned old prediction at a common physical epoch."""
    sample = np.array([0.0, 150.0, 300.0])
    current = propagate(new, origin, sample)
    previous = propagate(old, origin, sample)
    p, v = current["position_km"], current["velocity_km_s"]
    inertial = v.copy()
    inertial[..., 0] -= EARTH_ROTATION_RAD_S * p[..., 1]
    inertial[..., 1] += EARTH_ROTATION_RAD_S * p[..., 0]
    phase = float(
        np.median(
            np.sum((previous["position_km"] - p) * inertial, axis=2) / np.sum(inertial**2, axis=2)
        )
    )
    pad = int(np.ceil(abs(phase))) + 3
    knots = np.arange(np.floor(min(times)) - pad, np.ceil(max(times)) + pad + 1)
    previous = propagate(old, origin, knots)
    po, vo = phase_shifted_states(previous, times, -phase)
    current = propagate(new, origin, times)
    return current["position_km"][0] - po[0], current["velocity_km_s"][0] - vo[0], phase


def fit_shrinkage(pairs):
    """Ridge AR coefficient, robust by satellite, bounded to avoid extrapolation."""
    if not pairs:
        return 0.0
    x = np.array([r["predictor"] for r in pairs]) / 0.3
    y = np.array([r["target"] for r in pairs]) / 0.3
    alpha = 0.0
    for _ in range(8):
        error = np.sqrt(np.mean((y - alpha * x) ** 2, axis=1))
        weight = np.minimum(1.0, 2.0 / np.maximum(error, 1e-12))
        numerator = np.sum(weight[:, None] * x * y)
        denominator = np.sum(weight[:, None] * x * x) + 0.25 * len(pairs)
        alpha = float(np.clip(numerator / denominator, -1, 1))
    return alpha


def training_pairs(data):
    records = []
    sample = np.array([0.0, 150.0, 300.0])
    for norad, row in data["candidates"].items():
        history = sorted(row["past_versions"], key=lambda r: r["epoch"])
        for k in range(2, len(history)):
            a, b, c = history[k - 2 : k + 1]
            ratio = (c["epoch"] - b["epoch"]) / (b["epoch"] - a["epoch"])
            dp, dv, _ = innovation(b, a, c["epoch"], sample)
            target_p, target_v, _ = innovation(c, b, c["epoch"], sample)
            records.append(
                dict(
                    norad=int(norad),
                    terminal_epoch=c["epoch"],
                    collection_utc_ns=c["collected_utc_ns"],
                    predictor_available_utc_ns=max(a["collected_utc_ns"], b["collected_utc_ns"]),
                    last_for_satellite=k == len(history) - 1,
                    predictor=np.r_[dp.ravel(), 100 * dv.ravel()] * ratio,
                    target=np.r_[target_p.ravel(), 100 * target_v.ravel()],
                )
            )
    return records


def forecast_bank(scan, labels):
    if hasattr(scan, "causal_forecast_cache"):
        return scan.causal_forecast_cache
    data = causal_history(scan.case)
    pairs = training_pairs(data)
    alpha = fit_shrinkage(pairs)
    # Earlier triples train the hindcast; each last triple is evaluated without
    # that record. No GLRT observations are withheld or selected here.
    later = [r for r in pairs if r["last_for_satellite"]]
    hindcast_rows = []
    for record in later:
        earlier = [
            r
            for r in pairs
            if r["collection_utc_ns"] <= record["predictor_available_utc_ns"]
            and r["terminal_epoch"] < record["terminal_epoch"]
        ]
        coefficient = fit_shrinkage(earlier)
        hindcast_rows.append(
            dict(
                norad=record["norad"],
                training_pairs=len(earlier),
                coefficient=coefficient,
                zero_forecast_mean_square_km2=float(np.mean(record["target"] ** 2)),
                forecast_mean_square_km2=float(
                    np.mean((record["target"] - coefficient * record["predictor"]) ** 2)
                ),
            )
        )
    hindcast = dict(
        test_pairs=len(later),
        zero_forecast_rms_km=float(
            np.sqrt(np.mean([r["zero_forecast_mean_square_km2"] for r in hindcast_rows]))
        ),
        forecast_rms_km=float(
            np.sqrt(np.mean([r["forecast_mean_square_km2"] for r in hindcast_rows]))
        ),
        rows=hindcast_rows,
        state_metric_velocity_scaled_by_100_seconds=True,
    )
    bank = {k: v.copy() for k, v in scan.sky.items()}
    metadata = dict(coefficient=alpha, training_pairs=pairs, hindcast=hindcast, candidates={})
    available_labels = [j for j, n in enumerate(scan.norads) if str(int(n)) in data["candidates"]]
    if not set(labels).issubset(available_labels):
        raise ValueError("nominated candidate lacks causal history")
    for j in available_labels:
        n = str(int(scan.norads[j]))
        row = data["candidates"][n]
        latest = row["latest_causal"]
        previous = [r for r in row["past_versions"] if r["epoch"] < latest["epoch"]]
        if not previous:
            continue
        previous = max(previous, key=lambda r: r["epoch"])
        age = (data["origin_utc_ns"] - latest["epoch"]) / 1e9
        gap = (latest["epoch"] - previous["epoch"]) / 1e9
        # Forecast magnitude is limited by the innovation interval, rather than
        # allowing an arbitrarily old element to imply a huge extrapolation.
        ratio = float(np.clip(age / gap, 0, 1))
        dp, dv, phase = innovation(latest, previous, data["origin_utc_ns"], bank["time_s"])
        bank["position_km"][j] += alpha * ratio * dp
        bank["velocity_km_s"][j] += alpha * ratio * dv
        metadata["candidates"][n] = dict(
            ratio=ratio,
            phase_alignment_s=phase,
            position_correction_rms_km=float(np.sqrt(np.mean((alpha * ratio * dp) ** 2))),
        )
    scan.causal_forecast_cache = bank, metadata
    return bank, metadata
