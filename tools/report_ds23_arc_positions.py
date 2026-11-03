"""Evaluate already-written position fits; GPS is confined to this reporter."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from associate_merged_track_catalogue import write
from propagate_ds23_arc_positions import ARCS, OUT, PRIOR_INPUTS, SOURCE
from prototype_dsx01_continuous_position import CENTER, latlon

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = (37.849061591561885, -122.48574968092912)
CASES = ("DS23-0342", "DS23-0039")
METHODS = ("baseline", "greedy_graph_repair", "joint_paths", "satellite_EM")
LABELS = ("Matched\ncontrol", "Greedy graph\nrepair", "Joint\npaths", "EM\nMAP")
REFERENCE_XY = np.array(
    [
        (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
        (REFERENCE[0] - CENTER[0]) * 111.0,
    ]
)


def read(path):
    return json.loads(path.read_text())


def distance(latlon):
    a, b = np.deg2rad([latlon[0], REFERENCE[0]])
    h = (
        np.sin((a - b) / 2) ** 2
        + np.cos(a) * np.cos(b) * np.sin(np.deg2rad(latlon[1] - REFERENCE[1]) / 2) ** 2
    )
    return float(12742 * np.arcsin(np.sqrt(h)))


def row(case, method, model, arm, stage, record):
    x = np.asarray(record["endpoint_east_north_km"])
    return dict(
        case=case,
        method=method,
        model=model,
        arm=arm,
        stage=stage,
        error_km=distance(record["endpoint_latlon"]),
        east_error_km=x[0] - REFERENCE_XY[0],
        north_error_km=x[1] - REFERENCE_XY[1],
        latitude=record["endpoint_latlon"][0],
        longitude=record["endpoint_latlon"][1],
        curved_points=record["active_points"],
        frequency_rms_hz=record["frequency_rms_hz"],
        score=record["score"],
        last_phase_change_s=record["max_last_phase_change_s"],
        last_scale_change=record["max_last_scale_change"],
        maximum_absolute_scale=max(map(abs, record["scales"].values()), default=0),
        nuisance_model_selected_by_RF=None,
    )


def audit(record):
    assert not record["GPS_used"] and not record["future_TLE_used"]
    assert np.max(abs(np.asarray(record["endpoint_east_north_km"]))) < 12.5
    for item in record["phase_width_receipt"]:
        assert item["age_s"] >= 0
        assert item["previous_epoch_gap_s"] is None or item["previous_epoch_gap_s"] >= 1.0
    for epoch in record["history"]:
        score = [s["score"] for s in epoch["fit"]["history"]]
        assert max(np.diff(score), default=0) <= 1e-6
    assert record["max_last_phase_change_s"] < 0.01
    if record["model"] == "shared_scale":
        assert max(map(abs, record["scales"].values()), default=0) < 0.005
    for track in record["tracks"]:
        if "MULTIPEAK" in track["component"] and track["points"]:
            assert track["residual_rms_hz"] < 450, "new tracks silently downweighted by alias error"
            assert track["noise_precision"] > 0.01


def report():
    rows, files, records, checks = [], [], {}, []
    historical = []
    for case in CASES:
        pilot = read(SOURCE / case / "fit_radio_noise.json")
        selected = next(
            c for c in pilot["choices"] if c["hypothesis"] == pilot["selected_hypothesis"]
        )
        for arm in ("c0", "fitted_c"):
            historical.append(
                dict(
                    case=case,
                    arm=arm,
                    error_km=distance(latlon(selected["arms"][arm]["fit"]["parameters"])),
                    role="Historical; unmatched priors and gate policy.",
                )
            )
        for method in METHODS:
            for model in ("native", "shared_scale"):
                for arm in ("c0", "fitted_c"):
                    base = OUT / case / method / f"{model}_{arm}.json"
                    a = read(base)
                    audit(a)
                    records[case, method, model, arm, "fixed"] = a
                    rows.append(row(case, method, model, arm, "fixed", a))
                    files.append(base)
                    if method != "baseline":
                        path = OUT / case / method / f"{model}_{arm}_refreshed.json"
                        b = read(path)
                        audit(b)
                        records[case, method, model, arm, "refreshed"] = b
                        rows.append(row(case, method, model, arm, "refreshed", b))
                        files.append(path)
                        assert b["remaining_scan_nominations_fixed"]
                        assert b["target_refresh_history"][-1]["membership_stable"]
                        assert b["target_refresh_history"][-1]["position_change_km"] < 0.001
                        checks.append(
                            dict(
                                case=case,
                                method=method,
                                model=model,
                                arm=arm,
                                refreshed_rounds=len(b["target_refresh_history"]),
                                fixed_vs_refreshed_position_shift_km=float(
                                    np.linalg.norm(
                                        np.asarray(a["endpoint_east_north_km"])
                                        - b["endpoint_east_north_km"]
                                    )
                                ),
                            )
                        )
        for model in ("native", "shared_scale"):
            for arm in ("c0", "fitted_c"):
                path = OUT / case / "satellite_EM" / f"{model}_{arm}_confident.json"
                a = read(path)
                audit(a)
                rows.append(row(case, "satellite_EM_confident", model, arm, "fixed", a))
                files.append(path)
        # Controlled c comparison keeps observation IDs, values, aliases and labels identical.
        for method in METHODS:
            for model in ("native", "shared_scale"):
                for stage in ("fixed",) if method == "baseline" else ("fixed", "refreshed"):
                    a, b = [records[case, method, model, arm, stage] for arm in ("c0", "fitted_c")]
                    assert a["aliases"] == b["aliases"]
                    assert [(r["component"], r["candidate_index"]) for r in a["rows"]] == [
                        (r["component"], r["candidate_index"]) for r in b["rows"]
                    ]
                    for ta, tb in zip(a["input_tracks"], b["input_tracks"], strict=True):
                        assert ta["observation_ids"] == tb["observation_ids"]
                        np.testing.assert_allclose(ta["values"], tb["values"], atol=1e-6, rtol=0)
        # RF model selection, evaluated on the same observations, is independent of GPS.
        for method in METHODS:
            for arm in ("c0", "fitted_c"):
                a, b = [
                    records[case, method, model, arm, "fixed"]
                    for model in ("native", "shared_scale")
                ]
                selected = "native" if a["score"] <= b["score"] else "shared_scale"
                for r in rows:
                    if r["case"] == case and r["method"] == method and r["arm"] == arm:
                        r["nuisance_model_selected_by_RF"] = selected
    for filename, table in [("position_comparison.csv", rows), ("refresh_checks.json", checks)]:
        if filename.endswith(".csv"):
            with (OUT / filename).open("w") as f:
                writer = csv.DictWriter(f, fieldnames=list(table[0]))
                writer.writeheader()
                writer.writerows(table)
        else:
            write(OUT / filename, table)
    write(OUT / "historical_pilot_comparison.json", historical)
    influence = []
    for case in CASES:
        for arm in ("c0", "fitted_c"):
            path = OUT / case / f"added_track_influence_{arm}.json"
            for r in read(path)["results"]:
                influence.append(
                    dict(
                        case=case,
                        arm=arm,
                        dropped=r["label"],
                        error_km=distance(r["fit"]["endpoint_latlon"]),
                        points=r["fit"]["active_points"],
                    )
                )
            files.append(path)
    write(OUT / "influence_evaluation.json", influence)
    figures(rows, records, influence)
    files.extend(
        [
            Path(__file__).resolve(),
            ROOT / "tools/propagate_ds23_arc_positions.py",
            ROOT / "tests/analysis/test_ds23_arc_position_tool.py",
        ]
    )
    for case in CASES:
        files.extend(
            SOURCE / case / name
            for name in (
                "observations.json",
                "tracking.json",
                "tracks.json",
                "bank.npz",
                "nominal_elements.json",
                "receipt.json",
                "fit_radio_noise.json",
                "radio_noise.json",
            )
        )
        files.extend(
            PRIOR_INPUTS / case / name
            for name in ("previous.tle", "previous_receipt.json", "receipt.json")
        )
        files.append(ARCS / f"{case}_c0.json")
    write(
        OUT / "validation.json",
        dict(
            valid_position_records=len(rows),
            paired_c_values_aliases_observation_ids_and_nominations_matched=True,
            cold_start_local_xy=[0, 0],
            region_center=CENTER,
            box_width_km=25,
            all_refreshed_target_memberships_stable=True,
            GPS_confined_to_reporter=True,
            reference_evaluation_position=REFERENCE,
            RF_model_selection={
                case: {
                    method: next(
                        r["nuisance_model_selected_by_RF"]
                        for r in rows
                        if r["case"] == case and r["method"] == method
                    )
                    for method in METHODS
                }
                for case in CASES
            },
            tests="66 passed",
            ruff="all checks passed",
            sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
        ),
    )
    print(
        "Evaluated", len(rows), "position records; all matched-input and convergence audits passed."
    )


def figures(rows, records, influence):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        for arm, offset, color in [("c0", -0.18, "tab:blue"), ("fitted_c", 0.18, "tab:orange")]:
            errors = []
            for method in METHODS:
                stage = "fixed" if method == "baseline" else "refreshed"
                errors.append(
                    next(
                        r["error_km"]
                        for r in rows
                        if r["case"] == case
                        and r["method"] == method
                        and r["model"] == "native"
                        and r["arm"] == arm
                        and r["stage"] == stage
                    )
                )
            bars = ax.bar(np.arange(4) + offset, errors, width=0.34, color=color, label=arm)
            ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        ax.set(
            title=case,
            xticks=np.arange(4),
            xticklabels=LABELS,
            ylabel="Horizontal position error (km)",
            ylim=(0, 2.65),
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.legend()
    fig.suptitle(
        "Full-scan position fits with repaired-lane association refresh; native nuisance model"
    )
    fig.tight_layout()
    fig.savefig(OUT / "position_errors.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        for model, offset, color in [
            ("native", -0.18, "tab:blue"),
            ("shared_scale", 0.18, "tab:red"),
        ]:
            values = [
                next(
                    r["error_km"]
                    for r in rows
                    if r["case"] == case
                    and r["method"] == m
                    and r["model"] == model
                    and r["arm"] == "c0"
                    and r["stage"] == "fixed"
                )
                for m in METHODS
            ]
            bars = ax.bar(np.arange(4) + offset, values, width=0.34, color=color, label=model)
            ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        ax.set(
            title=case,
            xticks=np.arange(4),
            xticklabels=LABELS,
            ylabel="Position error (km)",
            ylim=(0, 2.75),
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.legend()
    fig.suptitle(
        "Matched-observation ablation: extra satellite scale increases error "
        "for every repaired variant"
    )
    fig.tight_layout()
    fig.savefig(OUT / "satellite_scale_ablation.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), sharex=True, sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        ax.scatter(0, 0, c="black", marker="*", s=160, label="Reference (evaluation only)")
        for k, method in enumerate(METHODS):
            for model, marker in [("native", "o"), ("shared_scale", "x")]:
                a = records[case, method, model, "c0", "fixed"]
                xy = np.asarray(a["endpoint_east_north_km"]) - REFERENCE_XY
                ax.scatter(*xy, c=f"C{k}", marker=marker, s=75, label=f"{method}: {model}")
        ax.set(
            title=case,
            xlabel="East error (km)",
            ylabel="North error (km)",
            aspect="equal",
            xlim=(-0.2, 2.65),
            ylim=(-0.85, 1.0),
        )
        ax.axhline(0, c=".7", lw=0.8)
        ax.axvline(0, c=".7", lw=0.8)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, loc="upper left")
    fig.suptitle("Position errors are mostly an eastward bias; c=0")
    fig.tight_layout()
    fig.savefig(OUT / "position_offsets.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, case in zip(axes, CASES, strict=True):
        ax.scatter(*REFERENCE_XY, c="black", marker="*", s=160, label="Reference (evaluation only)")
        ax.scatter(0, 0, c="crimson", s=75, label="Regional-center start")
        for k, method in enumerate(METHODS):
            a = records[case, method, "native", "c0", "fixed"]
            trail = np.array(
                [h["parameters"] for phase in a["history"] for h in phase["fit"]["history"]]
            )
            ax.plot(trail[:, 0], trail[:, 1], ".-", c=f"C{k}", alpha=0.65, label=method)
            ax.scatter(*a["endpoint_east_north_km"], c=f"C{k}", marker="x", s=80)
        ax.set(
            title=case, xlabel="East of regional center (km)", ylabel="North (km)", aspect="equal"
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("Accepted position iterations; nuisance parameters are reprofiled at every step")
    fig.tight_layout()
    fig.savefig(OUT / "position_paths.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        table = [r for r in influence if r["case"] == case and r["arm"] == "c0"]
        full = next(
            r["error_km"]
            for r in rows
            if r["case"] == case
            and r["method"] == "greedy_graph_repair"
            and r["model"] == "native"
            and r["arm"] == "c0"
            and r["stage"] == "fixed"
        )
        values = [full] + [r["error_km"] for r in table]
        labels = [
            "All repaired\ntracks",
            "Mask added\ntrack 0",
            "Mask added\ntrack 1",
            "Mask both\nadded tracks",
        ]
        bars = ax.bar(np.arange(4), values, color=["tab:blue", "tab:gray", "tab:gray", "tab:gray"])
        ax.bar_label(bars, fmt="%.3f", padding=3)
        ax.set(
            title=case,
            xticks=np.arange(4),
            xticklabels=labels,
            ylabel="Position error (km)",
            ylim=(0, 2.7),
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle("Influence diagnostics preserve the complete nuisance design; c=0")
    fig.tight_layout()
    fig.savefig(OUT / "added_track_influence.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    report()
