"""Compare six frozen GLRT/PSS lanes against causal historical Starlink TLEs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_paired_pss_bandwidth import product, windows, write

from leo.analysis.research.tle_shape_comparison import profile_shapes, unwrap_cfo
from leo.sky.propagation import MINIMUM_PLAUSIBLE_ALTITUDE_KM, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset
from leo.storage import RecordingStore

LANES = ("native25", "derived2p5", "recorded2p5")
COLORS = ("#157f91", "#c76524", "#7d58a0")
C_KM_S = 299792.458


def polynomial_diagnostics(t, y, degree=2):
    x = t - 1.125
    coef = np.polyfit(x, y - np.median(y), degree)
    residual = y - np.median(y) - np.polyval(coef, x)
    train = np.arange(len(t)) % 2 == 0
    alt = np.polyfit(x[train], y[train] - np.median(y), degree)
    held = y[~train] - np.median(y) - np.polyval(alt, x[~train])
    return dict(
        slope=float(coef[-2]),
        second_derivative=float(2 * coef[-3]),
        rms=float(np.sqrt(np.mean(residual**2))),
        mad=float(1.4826 * np.median(abs(residual - np.median(residual)))),
        alternate_rms=float(np.sqrt(np.mean(held**2))),
    )


def measurements(c, source, lock, out, root):
    records = []
    for lane, source_lane in (("native25", "native"), ("recorded2p5", "recorded")):
        b = c[source_lane]["binding"]
        start = c[f"{source_lane}_start_s"]
        ws = [
            w
            for w in windows(product(root, c[source_lane]))
            if w["global_start_time_s"] >= start - 1e-9
            and w["global_end_time_s"] <= start + 2.25 + 1e-9
        ]
        valid = [w for w in ws if w["passed_margin_gate"] and w["robust_line_available"]]
        t = np.array([w["global_robust_reference_time_s"] - start for w in valid])
        raw = np.array([w["robust_cfo_at_reference_hz"] for w in valid])
        epoch_s = np.array([w["global_epoch_device_sample"] / b["sample_rate_hz"] for w in valid])
        # Reduce modulo the frame before unwrapping, avoiding dependence on
        # which complete frame each overlapping acquisition selected.
        epoch_phase_ns = (
            np.unwrap((epoch_s % (1 / 750)) * 750 * 2 * np.pi) / (750 * 2 * np.pi) * 1e9
        )
        records.append(
            dict(
                method="GLRT",
                lane=lane,
                time_s=t.tolist(),
                value=unwrap_cfo(raw).tolist(),
                raw_cfo_hz=raw.tolist(),
                count=len(valid),
                window_count=len(ws),
                passing_fraction=sum(w["passed_margin_gate"] for w in ws) / len(ws),
                median_margin=float(np.median([w["glrt_margin"] for w in ws])),
                epoch_grid_ns=1e9 / b["sample_rate_hz"],
                epoch_time_s=(epoch_s - start).tolist(),
                epoch_phase_ns=epoch_phase_ns.tolist(),
                integer_epoch_diagnostics=polynomial_diagnostics(epoch_s - start, epoch_phase_ns),
            )
        )
    docs = [
        json.loads(p.read_text())
        for p in sorted((out / c["capture_id"]).glob("derived-glrt-*.json"))
    ]
    if len(docs) != 9:
        raise ValueError("incomplete derived GLRT replay")
    all_rows = [
        (d["output_device_sample_start"] / 2_500_000 - c["native_start_s"], w)
        for d in docs
        for w in d["windows"]
    ]
    valid = [(s, w) for s, w in all_rows if w["passed_margin_gate"] and w["robust_line_available"]]
    t = np.array([s + w["robust_reference_time_s"] for s, w in valid])
    raw = np.array([w["robust_cfo_at_reference_hz"] for _, w in valid])
    epoch_s = np.array(
        [
            s + c["native_start_s"] + (w["sample_start"] + w["epoch_sample"]) / 2_500_000
            for s, w in valid
        ]
    )
    epoch_phase_ns = np.unwrap((epoch_s % (1 / 750)) * 750 * 2 * np.pi) / (750 * 2 * np.pi) * 1e9
    records.append(
        dict(
            method="GLRT",
            lane="derived2p5",
            time_s=t.tolist(),
            value=unwrap_cfo(raw).tolist(),
            raw_cfo_hz=raw.tolist(),
            count=len(valid),
            window_count=len(all_rows),
            passing_fraction=sum(w["passed_margin_gate"] for _, w in all_rows) / len(all_rows),
            median_margin=float(np.median([w["glrt_margin"] for _, w in all_rows])),
            epoch_grid_ns=400.0,
            epoch_time_s=(epoch_s - c["native_start_s"]).tolist(),
            epoch_phase_ns=epoch_phase_ns.tolist(),
            integer_epoch_diagnostics=polynomial_diagnostics(
                epoch_s - c["native_start_s"], epoch_phase_ns
            ),
        )
    )
    pss = json.loads((source / "summary.json").read_text())
    for r in pss:
        if r["capture_id"] != c["capture_id"]:
            continue
        start = c["recorded_start_s" if r["lane"] == "recorded2p5" else "native_start_s"]
        records.append(
            dict(
                method="PSS",
                lane=r["lane"],
                time_s=(np.array(r["time_s"]) - start).tolist(),
                value=r["phase_s"],
                count=r["frame_count"],
                strong_fraction=r["strong_fraction"],
                raw_alternate_rms_ns=r["heldout_rms_ns"],
                raw_alternate_mad_ns=r["heldout_mad_ns"],
            )
        )
    locked = json.loads((lock / (c["capture_id"] + ".json")).read_text())
    ds = [d for d in locked["decisions"] if d["status"] == "accepted"]
    y = np.unwrap(np.array([d["observed_phase_s"] for d in ds]) * 750 * 2 * np.pi) / (
        750 * 2 * np.pi
    )
    records.append(
        dict(
            method="PSS-gated",
            lane="native25",
            time_s=[d["time_s"] - c["native_start_s"] for d in ds],
            value=y.tolist(),
            count=len(ds),
            gate_summary=locked["summary"],
        )
    )
    for r in records:
        r["capture_id"] = c["capture_id"]
        r["units"] = "Hz" if r["method"] == "GLRT" else "ns"
        if r["method"] != "GLRT":
            r["value"] = (np.array(r["value"]) * 1e9).tolist()
        r["diagnostics"] = polynomial_diagnostics(np.array(r["time_s"]), np.array(r["value"]))
    return records


def bank(c, ref, out):
    raw = (out / ref["snapshot_filename"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("snapshot hash mismatch")
    cat = parse_element_sets(raw.decode())
    observer = resolve_preset("spinnaker-sausalito")
    start = ref["measurement_start_utc_ns"]
    coarse = SamplingGrid(tuple(start + round(t * 1e9) for t in (0.0, 1.125, 2.25)), 1, 1.125)
    obs = observe_grid(propagate_grid(cat, coarse), observer, coarse)
    named = np.array(["STARLINK" in n.upper() for n in cat.names])
    # Causal selection concerns collection time. Some archived element epochs
    # lie in the future; count these explicitly and exclude from this comparison.
    epochs = np.array(cat.element_epoch_utc_ns(), dtype=np.int64)
    eligible = (
        named
        & (epochs <= start)
        & obs.usable
        & (obs.altitude_km > MINIMUM_PLAUSIBLE_ALTITUDE_KM).all(axis=1)
    )
    # Keep every above-horizon object for mask sensitivity; no antenna pointing
    # authority exists in the selected manifests.
    indices = np.flatnonzero(eligible & (obs.elevation_deg[:, 1] >= 0))
    if not len(indices):
        raise ValueError("no above-horizon historical Starlink objects")
    t = np.linspace(0, 2.25, 226)
    grid = SamplingGrid(tuple(start + round(x * 1e9) for x in t), 112, 0.01)
    fine = observe_grid(propagate_grid(cat, grid, indices=indices.tolist()), observer, grid)
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect(c["capture_id"])
        if (
            "sha256:" + bundle.manifest_sha256.removeprefix("sha256:")
            != c["native"]["manifest_digest"]
        ):
            raise ValueError("manifest changed since cohort selection")
        manifest = bundle.manifest.model_dump(mode="json")
    finally:
        store.close()
    plan = next(
        p
        for p in manifest["capture_plan"]["radio_plans"]
        if p["radio_id"] == c["native"]["binding"]["radio_id"]
    )
    rf = plan["profile_revision"]["profile"]["lnb_lo_hz"] + plan["pilot_if_center_frequency_hz"]
    candidates = [
        dict(
            catalogue_index=int(i),
            norad_id=cat.satellite_numbers[i],
            name=cat.names[i],
            elevation_deg=float(obs.elevation_deg[i, 1]),
            azimuth_deg=float(obs.azimuth_deg[i, 1]),
            element_age_hours=float((start - epochs[i]) / 3.6e12),
        )
        for i in indices
    ]
    delay = fine.range_km / C_KM_S * 1e9
    cfo = -rf * fine.range_rate_km_s / C_KM_S
    for i, r in enumerate(candidates):
        r["predicted_cfo_rate_hz_s"] = float(np.polyfit(t - 1.125, cfo[i], 2)[1])
        r["predicted_timing_curvature_ns_s2"] = float(2 * np.polyfit(t - 1.125, delay[i], 2)[0])
    audit = dict(
        **ref,
        observer=observer.model_dump(mode="json"),
        observer_confirmed=False,
        rf_pilot_frequency_hz=rf,
        catalogue_count=len(cat),
        starlink_count=int(named.sum()),
        future_element_epoch_count=int((named & (epochs > start)).sum()),
        eligible_count=int(eligible.sum()),
        above_horizon_count=len(indices),
        above_10deg_count=sum(r["elevation_deg"] >= 10 for r in candidates),
        no_pointing_filter=True,
        candidates=candidates,
    )
    write(out / c["capture_id"] / "tle-candidates.json", audit)
    np.savez_compressed(
        out / c["capture_id"] / "tle-predictions.npz", time_s=t, delay_ns=delay, cfo_hz=cfo
    )
    return t, delay, cfo, audit


def compare(r, tgrid, values, candidates, *, degree, mask):
    t, y = np.array(r["time_s"]), np.array(r["value"])
    selected = [i for i, c in enumerate(candidates) if c["elevation_deg"] >= mask]
    p = np.array([np.interp(t, tgrid, values[i]) for i in selected])
    result = profile_shapes(t, y, p, nuisance_degree=degree, split_s=1.35)
    threshold = r["diagnostics"]["alternate_rms"]
    rankings = []
    for i in result["order"]:
        rankings.append(
            dict(
                **candidates[selected[i]],
                early_rms=float(result["early_rms"][i]),
                late_rms=float(result["late_rms"][i]),
                nuisance_coefficients=result["coefficients"][i].tolist(),
                late_distance_from_early_winner=float(
                    result["late_separation_from_early_winner"][i]
                ),
            )
        )
    return dict(
        nuisance_degree=degree,
        elevation_mask_deg=mask,
        candidate_count=len(selected),
        empirical_shape_resolution=threshold,
        within_empirical_resolution_count=int(
            (result["late_separation_from_early_winner"] <= threshold).sum()
        ),
        early_winner_late_rank=int(
            np.where(np.argsort(result["late_rms"]) == result["order"][0])[0][0] + 1
        ),
        rankings=rankings,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    cs = json.loads((args.source / "selection.json").read_text())["selected"]
    refs = json.loads((args.output / "tle-snapshots.json").read_text())
    all_records, audits = [], []
    fig, axes = plt.subplots(5, 2, figsize=(13, 16), constrained_layout=True)
    fig2, ax2 = plt.subplots(5, 2, figsize=(13, 16), constrained_layout=True)
    fig3, ax3 = plt.subplots(5, 1, figsize=(10, 13), constrained_layout=True)
    for row, (c, ref) in enumerate(zip(cs, refs, strict=True)):
        recs = measurements(c, args.source, args.lock, args.output, Path("/srv/bulk/leo"))
        tgrid, delay, cfo, audit = bank(c, ref, args.output)
        audits.append(audit)
        visible = [
            i for i, candidate in enumerate(audit["candidates"]) if candidate["elevation_deg"] >= 10
        ]
        detrended = np.array(
            [v - np.polyval(np.polyfit(tgrid, v, 1), tgrid) for v in delay[visible]]
        )
        ax3[row].fill_between(
            tgrid,
            detrended.min(axis=0),
            detrended.max(axis=0),
            color="#bbbbbb",
            alpha=0.6,
            label="Geometric TLE delay envelope",
        )
        for r in recs:
            if r["lane"] != "native25" or r["method"] == "PSS":
                continue
            tx = np.array(r["epoch_time_s"] if r["method"] == "GLRT" else r["time_s"])
            yx = np.array(r["epoch_phase_ns"] if r["method"] == "GLRT" else r["value"])
            ax3[row].scatter(
                tx,
                yx - np.polyval(np.polyfit(tx, yx, 1), tx),
                s=4,
                color=COLORS[0] if r["method"] == "GLRT" else "black",
                alpha=0.6,
                label="GLRT integer epoch"
                if r["method"] == "GLRT"
                else "PSS accepted fractional timing",
            )
        ax3[row].set_title(c["capture_id"][-6:])
        ax3[row].set_ylabel("Timing minus fitted line (ns)")
        ax3[row].set_xlabel("Seconds into selected interval")
        ax3[row].grid(alpha=0.2)
        for r in recs:
            if r["method"] == "GLRT":
                epoch = dict(
                    time_s=r["epoch_time_s"],
                    value=r["epoch_phase_ns"],
                    diagnostics=r["integer_epoch_diagnostics"],
                )
                r["integer_epoch_tle_primary"] = compare(
                    epoch, tgrid, delay, audit["candidates"], degree=1, mask=10
                )
            values = cfo if r["method"] == "GLRT" else delay
            degree = 0 if r["method"] == "GLRT" else 1
            r["primary"] = compare(r, tgrid, values, audit["candidates"], degree=degree, mask=10)
            r["clock_drift_sensitivity"] = compare(
                r, tgrid, values, audit["candidates"], degree=degree + 1, mask=10
            )
            r["horizon_sensitivity"] = compare(
                r, tgrid, values, audit["candidates"], degree=degree, mask=0
            )
            col = 0 if r["method"] == "GLRT" else 1
            color = "black" if r["method"] == "PSS-gated" else COLORS[LANES.index(r["lane"])]
            t, y = np.array(r["time_s"]), np.array(r["value"])
            # Removing a fitted line in timing exposes curvature, avoiding an
            # apparently clean slope that is completely degenerate with clock.
            centered = y - np.median(y) if col == 0 else y - np.polyval(np.polyfit(t, y, 1), t)
            axes[row, col].scatter(
                t,
                centered,
                s=2,
                alpha=0.45,
                color=color,
                label=r["lane"] + (" gated" if r["method"] == "PSS-gated" else ""),
            )
            j = 3 if r["method"] == "PSS-gated" else LANES.index(r["lane"])
            ranks = r["primary"]["rankings"]
            ax2[row, col].scatter(j, ranks[0]["late_rms"], color=color, marker="o")
            ax2[row, col].scatter(
                j + 0.12,
                r["clock_drift_sensitivity"]["rankings"][0]["late_rms"],
                color=color,
                marker="x",
            )
            ax2[row, col].text(
                j, ranks[0]["late_rms"] * 1.08, str(ranks[0]["norad_id"]), fontsize=7, ha="center"
            )
            print(
                c["capture_id"][-6:],
                r["method"],
                r["lane"],
                "slope/curvature",
                r["diagnostics"]["slope"],
                r["diagnostics"]["second_derivative"],
                "best",
                ranks[0]["name"],
                "late RMS",
                ranks[0]["late_rms"],
                "close",
                r["primary"]["within_empirical_resolution_count"],
                "drift-close",
                r["clock_drift_sensitivity"]["within_empirical_resolution_count"],
                flush=True,
            )
        for col in (0, 1):
            label = "GLRT CFO minus median" if col == 0 else "PSS timing minus fitted line"
            axes[row, col].set_title(f"{c['capture_id'][-6:]} · {label}")
            axes[row, col].set_ylabel("Hz" if col == 0 else "ns")
            axes[row, col].set_xlabel("Seconds into selected interval")
            axes[row, col].grid(alpha=0.2)
            ax2[row, col].set_title(c["capture_id"][-6:] + (" · GLRT" if col == 0 else " · PSS"))
            ax2[row, col].set_yscale("log")
            ax2[row, col].set_ylabel(
                "Late TLE residual RMS (Hz)" if col == 0 else "Late TLE residual RMS (ns)"
            )
            ax2[row, col].set_xticks(
                range(3 if col == 0 else 4),
                ["25M", "2.5M derived", "2.5M other"] + ([] if col == 0 else ["25M gated"]),
                fontsize=8,
            )
            ax2[row, col].grid(alpha=0.2)
            ax2[row, col].margins(y=0.25)
        all_records.extend(recs)
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].legend(fontsize=8)
    fig.suptitle(
        "Measured curves · same five 2.25-second GLRT-selected intervals\n"
        "PSS includes every peak in the selected track; black points pass the earlier causal gate"
    )
    fig.savefig(args.output / "six-lane-measured-curves.png", dpi=150)
    plt.close(fig)
    fig2.suptitle(
        "Historical TLE shape tests · provisional Sausalito site, elevation ≥10°\n"
        "Early 60% selects candidate; late 40% RMS shown · circle: primary clock model; "
        "×: one extra drift term\n"
        "Numbers are NORAD IDs of early winners, not satellite identifications"
    )
    fig2.savefig(args.output / "tle-heldout-comparison.png", dpi=150)
    plt.close(fig2)
    ax3[0].legend(fontsize=8)
    fig3.suptitle(
        "Timing curvature does not match uncompensated geometric delay\n"
        "25 MS/s GLRT and gated PSS · each curve has its own full-interval line removed\n"
        "Historical Starlink TLEs above 10° · provisional Sausalito site"
    )
    fig3.savefig(args.output / "timing-curvature-versus-tle.png", dpi=150)
    plt.close(fig3)
    write(args.output / "comparison.json", all_records)
    write(args.output / "catalogue-audit.json", audits)
    fields = [
        "capture_id",
        "method",
        "lane",
        "count",
        "units",
        "slope",
        "second_derivative",
        "alternate_rms",
        "best_norad_id",
        "early_rms",
        "late_rms",
        "near_count",
        "drift_near_count",
    ]
    with (args.output / "measurement-summary.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in all_records:
            best = r["primary"]["rankings"][0]
            writer.writerow(
                {
                    **{k: r[k] for k in fields[:5]},
                    **{k: r["diagnostics"][k] for k in fields[5:8]},
                    "best_norad_id": best["norad_id"],
                    "early_rms": best["early_rms"],
                    "late_rms": best["late_rms"],
                    "near_count": r["primary"]["within_empirical_resolution_count"],
                    "drift_near_count": r["clock_drift_sensitivity"][
                        "within_empirical_resolution_count"
                    ],
                }
            )
    with (args.output / "tle-rankings.csv").open("w") as f:
        fields = [
            "capture_id",
            "method",
            "lane",
            "scenario",
            "early_rank",
            "norad_id",
            "name",
            "elevation_deg",
            "element_age_hours",
            "early_rms",
            "late_rms",
            "late_distance_from_early_winner",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in all_records:
            for scenario in ("primary", "clock_drift_sensitivity", "horizon_sensitivity"):
                for rank, candidate in enumerate(r[scenario]["rankings"], 1):
                    writer.writerow(
                        dict(
                            capture_id=r["capture_id"],
                            method=r["method"],
                            lane=r["lane"],
                            scenario=scenario,
                            early_rank=rank,
                            **candidate,
                        )
                    )


if __name__ == "__main__":
    main()
