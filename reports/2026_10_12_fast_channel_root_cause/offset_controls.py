"""Random grouped, train-only nuisance controls conditional on frozen satellite fits."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from leo.analysis.regional_position_score import circular

SEED = 20261012


def design(times, rf, rx, channel, model, c_enabled=True):
    time = (times - 150) / 150
    frequency = (rf - 11584687500) / 1e9
    high = channel >= 5
    columns = [rx == 0, (rx == 0) * time, rx == 1, (rx == 1) * time]
    names = ["a0", "b0_x150", "a1", "b1_x150"]
    if c_enabled:
        if model == "receiver-rf":
            columns.extend([frequency * (rx == 0), frequency * (rx == 1)])
            names.extend(["c0", "c1"])
        else:
            columns.append(frequency)
            names.append("c")
    if model == "shared-step":
        columns.append(high)
        names.append("step")
    if model in ("receiver-step", "receiver-step-drift"):
        columns.extend([high * (rx == 0), high * (rx == 1)])
        names.extend(["step0", "step1"])
    if model == "receiver-step-drift":
        columns.extend([high * (rx == 0) * time, high * (rx == 1) * time])
        names.extend(["step_drift0_x150", "step_drift1_x150"])
    return np.column_stack(columns).astype(float), names


def fit_nuisance(x, y, weights, train, names):
    initial = np.linalg.lstsq(
        x[train] * np.sqrt(weights[train, None]), y[train] * np.sqrt(weights[train]), rcond=None
    )[0]
    low = np.full(len(names), -200000.0)
    high = -low
    for i, name in enumerate(names):
        if name.startswith("c"):
            low[i], high[i] = -5000, 5000
        if "x150" in name:
            low[i], high[i] = -9000, 9000
    initial = np.clip(initial, low + 1e-6, high - 1e-6)
    fit = least_squares(
        lambda v: np.sqrt(weights[train]) * circular(y[train] - x[train] @ v) / 125,
        initial,
        bounds=(low, high),
        loss="soft_l1",
        max_nfev=500,
        xtol=1e-12,
        ftol=1e-12,
        gtol=1e-12,
        x_scale="jac",
    )
    return fit.x


def stats(residual, weights, mask):
    return dict(
        count=int(mask.sum()),
        rms_hz=float(np.sqrt(np.average(residual[mask] ** 2, weights=weights[mask]))),
        median_hz=float(np.median(residual[mask])),
        p95_abs_hz=float(np.quantile(abs(residual[mask]), 0.95)),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arrays", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    a = np.load(args.arrays)
    n = len(a["times_s"])
    target = np.zeros(n)
    weights = np.zeros(n)
    winner = np.zeros(n, dtype=int)
    orbit = np.zeros(n)
    for case in ("ch1_4", "ch5_8"):
        ix = a[case + "_rows"]
        resp = a[case + "_responsibilities"]
        best = resp.argmax(axis=1)
        j = np.arange(len(ix))
        orbit[ix] = a[case + "_prediction"][j, best]
        weights[ix] = resp[j, best]
        winner[ix] = a[case + "_numbers"][best]
    target = circular(a["measured_hz"] - orbit)
    support = weights >= 0.8
    # Whole 5-second blocks include both receivers and every channel group.
    groups = np.floor(a["times_s"] / 5).astype(int)
    unique = np.unique(groups)
    rng = np.random.default_rng(SEED)
    heldout = np.sort(rng.choice(unique, size=max(1, int(round(0.2 * len(unique)))), replace=False))
    test = np.isin(groups, heldout) & support
    train = (~np.isin(groups, heldout)) & support
    results = []
    residual_rows = []
    for rf_policy in (
        "recorded",
        "fixed-low",
        "fixed-high",
        "rx0-low-rx1-high",
        "rx0-high-rx1-low",
    ):
        rf = a["rf_hz"].copy()
        upper = a["channel"] >= 5
        if rf_policy == "fixed-low":
            rf[upper] -= 850000000
        if rf_policy == "fixed-high":
            rf[~upper] += 850000000
        if rf_policy == "rx0-low-rx1-high":
            rf[upper & (a["receiver"] == 0)] -= 850000000
            rf[(~upper) & (a["receiver"] == 1)] += 850000000
        if rf_policy == "rx0-high-rx1-low":
            rf[upper & (a["receiver"] == 1)] -= 850000000
            rf[(~upper) & (a["receiver"] == 0)] += 850000000
        y = circular(a["measured_hz"] - orbit * rf / a["rf_hz"])
        models = (
            ("shared-rf", "receiver-rf", "shared-step", "receiver-step", "receiver-step-drift")
            if rf_policy == "recorded"
            else ("receiver-step",)
        )
        for model in models:
            for enabled in (False, True):
                x, names = design(a["times_s"], rf, a["receiver"], a["channel"], model, enabled)
                beta = fit_nuisance(x, y, weights, train, names)
                residual = circular(y - x @ beta)
                row = dict(
                    rf_policy=rf_policy,
                    model=model,
                    arm="fitted-c" if enabled else "zero-c",
                    coefficients=dict(zip(names, map(float, beta), strict=True)),
                    train=stats(residual, weights, train),
                    heldout=stats(residual, weights, test),
                    by_lane={},
                )
                if rf_policy == "recorded" and model == "receiver-step" and enabled:
                    # Resample complete training blocks. These are conditional
                    # nuisance intervals, not spacecraft/localization intervals.
                    sample_rng = np.random.default_rng(SEED + 1)
                    train_groups = np.unique(groups[train])
                    samples = []
                    for _ in range(200):
                        drawn = sample_rng.choice(train_groups, len(train_groups), replace=True)
                        counts = np.bincount(drawn, minlength=int(groups.max()) + 1)
                        w = weights[train] * counts[groups[train]]
                        value = np.linalg.lstsq(
                            x[train] * np.sqrt(w[:, None]), y[train] * np.sqrt(w), rcond=None
                        )[0]
                        samples.append(value)
                    quantiles = np.quantile(np.array(samples), [0.025, 0.975], axis=0)
                    row["training_block_bootstrap_95pct"] = {
                        name: list(map(float, quantiles[:, i])) for i, name in enumerate(names)
                    }
                    row["bootstrap_replicates"] = 200
                    row["bootstrap_seed"] = SEED + 1
                for rx in (0, 1):
                    for band in (False, True):
                        mask = test & (a["receiver"] == rx) & (upper == band)
                        row["by_lane"][f"rx{rx}-" + ("ch5-8" if band else "ch1-4")] = stats(
                            residual, weights, mask
                        )
                results.append(row)
                if rf_policy == "recorded" and enabled and model in ("shared-rf", "receiver-step"):
                    for i in np.flatnonzero(support):
                        residual_rows.append(
                            dict(
                                window=i,
                                group=int(groups[i]),
                                split="heldout" if test[i] else "train",
                                model=model,
                                receiver=int(a["receiver"][i]),
                                channel=int(a["channel"][i]),
                                time_s=float(a["times_s"][i]),
                                catalog_number=int(winner[i]),
                                weight=float(weights[i]),
                                target_hz=float(target[i]),
                                residual_hz=float(residual[i]),
                            )
                        )
    full = a["ch1_8_responsibilities"]
    fullmass = full.sum(axis=1)
    original_lanes = []
    for rx in (0, 1):
        for high in (False, True):
            mask = (a["receiver"] == rx) & ((a["channel"] >= 5) == high)
            original_lanes.append(
                dict(
                    receiver=rx,
                    high_group=high,
                    windows=int(mask.sum()),
                    posterior_signal_mass=float(fullmass[mask].sum()),
                    strong_assignments=int((full.max(axis=1)[mask] >= 0.8).sum()),
                    frozen_half_strong_assignments=int((support & mask).sum()),
                )
            )
    result = dict(
        seed=SEED,
        group_policy=(
            "Whole 5-second blocks randomized jointly over both receivers and all channels."
        ),
        heldout_groups=heldout.tolist(),
        train_groups=np.setdiff1d(unique, heldout).tolist(),
        support_count=int(support.sum()),
        train_count=int(train.sum()),
        heldout_count=int(test.sum()),
        validation_scope=(
            "Conditional nuisance-model diagnostic. Satellite candidates, shifts, "
            "positions and support were frozen from the all-data half-channel "
            "exploratory fits. Only nuisance coefficients are learned from training "
            "blocks; this is not an independent validation of satellite identity "
            "or localization."
        ),
        controls=results,
        original_full_lanes=original_lanes,
    )
    step_fit = next(
        r
        for r in results
        if r["rf_policy"] == "recorded" and r["model"] == "receiver-step" and r["arm"] == "fitted-c"
    )
    x, names = design(a["times_s"], a["rf_hz"], a["receiver"], a["channel"], "receiver-step", True)
    beta = np.array([step_fit["coefficients"][name] for name in names])
    beta[names.index("step0")] = beta[names.index("step1")] = 0
    common_residual = circular(target - x @ beta)
    cross_satellites = []
    for rx in (0, 1):
        for number in np.unique(winner[support]):
            low = support & (a["receiver"] == rx) & (winner == number) & (a["channel"] <= 4)
            high = support & (a["receiver"] == rx) & (winner == number) & (a["channel"] >= 5)
            if min(low.sum(), high.sum()) >= 10:
                cross_satellites.append(
                    dict(
                        receiver=rx,
                        catalog_number=int(number),
                        low_windows=int(low.sum()),
                        high_windows=int(high.sum()),
                        median_high_minus_low_hz=float(
                            np.median(common_residual[high]) - np.median(common_residual[low])
                        ),
                    )
                )
    result["cross_satellite_steps"] = cross_satellites
    (args.output / "offset-controls.json").write_text(json.dumps(result, indent=2) + "\n")
    with (args.output / "offset-residuals.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(residual_rows[0]))
        writer.writeheader()
        writer.writerows(residual_rows)
    for row in results:
        print(
            row["rf_policy"],
            row["model"],
            row["arm"],
            row["heldout"]["rms_hz"],
            row["coefficients"],
        )


if __name__ == "__main__":
    main()
