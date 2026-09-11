#!/usr/bin/env python3
"""Paired timing/CFO translation checks on native and decimated historical IQ."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from evaluate_scan_glrt_rms import bootstrap_scan_ratio, rms, write_json
from replay_historic_glrt_joint import configurations
from replay_scan_glrt_search import alias_difference, frequency_shift

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration, acquire_symbolwise
from leo.analysis.starlink.pilot_methods import refine_glrt64_epochs
from leo.storage.persistent_hop import PersistentHopIqStore, PersistentHopStoredCi16Reader


def delay_signal(values, fs, delay_s):
    """Exact translation of the periodic bandlimited interpolant; crop guards later."""
    phase = np.exp(-2j * np.pi * np.fft.fftfreq(len(values), d=1 / fs) * delay_s)
    return np.fft.ifft(np.fft.fft(values) * phase)


def half_rate(values):
    # Odd symmetric FIR; "same" removes the 40-sample group delay before decimation.
    n = np.arange(-40, 41)
    taps = 0.44 * np.sinc(0.44 * n) * np.kaiser(len(n), 8.6)
    taps /= taps.sum()
    return np.convolve(values, taps, mode="same")[::2]


def timing_difference(a, b):
    period = 1 / 750
    return (a - b + period / 2) % period - period / 2


def choose(candidates, reference_s):
    selected = [
        c
        for c in candidates
        if c["cfo_hz"] is not None
        and c["margin"] >= 0.025
        and abs(timing_difference(c["integer_epoch_s"], reference_s)) <= 800e-9
    ]
    return max(selected, key=lambda c: (c["exact_score"], -c["rank"])) if selected else None


def make_plan(source):
    old = json.loads((source / "plan.json").read_text())
    selected = []
    for scan in old["selection"]:
        if scan["sample_rate_hz"] != 5000000:
            continue
        evidence = json.loads(Path(scan["source_evidence"]).read_text())
        lane = next(s for s in evidence["series"] if s["tracklet_id"] == scan["tracklet_id"])
        probes = []
        for index in np.linspace(0, scan["probes"] - 1, 6).round().astype(int):
            obs = lane["observations"][index]
            seed = int(
                hashlib.sha256(("rates-20260911:" + obs["candidate_id"]).encode()).hexdigest()[:16],
                16,
            )
            rng = np.random.default_rng(seed)
            probes.append(
                {
                    "index": int(index),
                    "candidate_id": obs["candidate_id"],
                    "delays_ns": (-300 + (np.arange(4) + rng.random(4)) * 150).tolist(),
                    "shifts_hz": (-2000 + (np.arange(4) + rng.random(4)) * 1000).tolist(),
                }
            )
        selected.append({**scan, "selected_probes": probes})
    return {
        "selection": selected,
        "sample_rates_hz": [2500000, 5000000],
        "fine_steps_hz": [500, 250],
        "conditioned_step_hz": 100,
        "grids": [512, 8192],
        "window_ms": 20,
        "source_read_ms": 21,
        "crop_start_ms": 0.5,
        "target_phase_radius_ns": 800,
        "decimation": (
            "81-tap symmetric Kaiser(8.6) windowed-sinc low-pass, cutoff 0.22 cycles "
            "per input sample; delay compensated; take even samples."
        ),
        "selection_policy": (
            "Three 5 Msps scans from earlier joint replay; six evenly indexed probes "
            "per longest lane, before inspecting new outcomes."
        ),
        "limits": (
            "Paired digital rate/bandwidth comparison on same physical observation. "
            "Decimation is not an independent native 2.5 Msps hardware recording. "
            "Shift recovery is relative consistency, not absolute timing or CFO accuracy."
        ),
    }


def replay(args, plan):
    started = time.monotonic()
    store = PersistentHopIqStore.open_read_only(Path("/srv/bulk/leo"))
    for scan in plan["selection"]:
        dest = args.output / "raw" / f"{scan['session_id']}.json"
        if dest.exists():
            continue
        path = Path(scan["source_evidence"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != scan["evidence_sha256"]:
            raise ValueError("source evidence changed")
        evidence = json.loads(path.read_text())
        lane = next(s for s in evidence["series"] if s["tracklet_id"] == scan["tracklet_id"])
        capture = store.inspect(scan["session_id"])
        reader = PersistentHopStoredCi16Reader(store, capture)
        starts, cursor = {}, 0
        for visit in capture.manifest.receipt.visits:
            starts[visit.visit_index] = cursor
            cursor += visit.valid_sample_count
        rows = []
        for probe in scan["selected_probes"]:
            obs = lane["observations"][probe["index"]]
            if obs["candidate_id"] != probe["candidate_id"] or obs["probe_index"] != 0:
                raise ValueError("probe binding changed")
            raw = reader.read_valid_ci16(starts[obs["visit_index"]], 105000)
            col = reader.receiver_ids.index(obs["receiver_id"])
            native = raw[:, col, 0].astype(float) + 1j * raw[:, col, 1].astype(float)
            versions = {5000000: native, 2500000: half_rate(native)}
            reference_s = (obs["persisted"]["integer_epoch_sample"] / 5e6 - 0.0005) % (1 / 750)
            cases = (
                [("baseline", 0.0)]
                + [("delay_ns", d) for d in probe["delays_ns"]]
                + [("shift_hz", f) for f in probe["shifts_hz"]]
            )
            calibration = ReceiverFrequencyCalibration(str(obs["receiver_id"]), 0, "0" * 64)
            for fs, values in versions.items():
                crop = round(fs * 0.0005)
                for kind, amount in cases:
                    if time.monotonic() - started > args.max_seconds:
                        raise TimeoutError("bounded sample-rate replay exhausted wall allowance")
                    transformed = (
                        delay_signal(values, fs, amount * 1e-9)
                        if kind == "delay_ns"
                        else frequency_shift(values, fs, amount)
                        if kind == "shift_hz"
                        else values
                    )
                    iq = transformed[crop : crop + fs // 50]
                    for fine in plan["fine_steps_hz"]:
                        config = replace(
                            configurations(fs)[f"fine{fine}_conditioned100"],
                            maximum_probe_samples=len(iq),
                        )
                        before = time.perf_counter()
                        acquisition = acquire_symbolwise(
                            iq, fs, calibration, edge=lane["edge"], config=config
                        )
                        acquisition_s = time.perf_counter() - before
                        for grid in plan["grids"]:
                            before = time.perf_counter()
                            refined = refine_glrt64_epochs(
                                iq,
                                fs,
                                integer_epoch_samples=[
                                    c.refined_epoch_sample for c in acquisition.candidates
                                ],
                                acquired_cfo_hz=[c.absolute_cfo_hz for c in acquisition.candidates],
                                edge=lane["edge"],
                                glrt_size=grid,
                            )
                            scoring_s = time.perf_counter() - before
                            candidates = [
                                {
                                    "rank": c.rank,
                                    "integer_epoch_s": c.refined_epoch_sample / fs,
                                    "epoch_s": (
                                        c.refined_epoch_sample + r.fractional_epoch_offset_samples
                                    )
                                    / fs
                                    if r.fractional_epoch_offset_samples is not None
                                    else None,
                                    "fraction_samples": r.fractional_epoch_offset_samples,
                                    "acquired_cfo_hz": c.absolute_cfo_hz,
                                    "cfo_hz": r.fractional_tracking_cfo_hz,
                                    "margin": r.fractional_margin,
                                    "exact_score": r.fractional_exact_score,
                                    "status": r.status.value,
                                }
                                for c, r in zip(acquisition.candidates, refined, strict=True)
                            ]
                            rows.append(
                                {
                                    "candidate_id": probe["candidate_id"],
                                    "index": probe["index"],
                                    "fs": fs,
                                    "fine_step_hz": fine,
                                    "grid": grid,
                                    "case": kind,
                                    "amount": amount,
                                    "reference_epoch_s": reference_s,
                                    "target": choose(candidates, reference_s),
                                    "candidates": candidates,
                                    "acquisition_s": acquisition_s,
                                    "scoring_s": scoring_s,
                                }
                            )
            print(
                f"{scan['session_id']} probe {probe['index']} complete "
                f"({time.monotonic() - started:.1f}s)",
                flush=True,
            )
        write_json(
            dest,
            {
                "session_id": scan["session_id"],
                "manifest_sha256": capture.manifest_sha256,
                "rows": rows,
            },
        )
    print(f"Completed paired replay in {time.monotonic() - started:.1f}s", flush=True)


def summarize(args, plan):
    docs = [json.loads(p.read_text()) for p in sorted((args.output / "raw").glob("*.json"))]
    if {d["session_id"] for d in docs} != {s["session_id"] for s in plan["selection"]}:
        raise ValueError("incomplete frozen scan inventory")
    rows = [{**r, "session_id": d["session_id"]} for d in docs for r in d["rows"]]
    details = []
    for scan in plan["selection"]:
        expected = {
            (p["candidate_id"], fs, fine, grid, kind, amount)
            for p in scan["selected_probes"]
            for fs in plan["sample_rates_hz"]
            for fine in plan["fine_steps_hz"]
            for grid in plan["grids"]
            for kind, amount in [("baseline", 0.0)]
            + [("delay_ns", d) for d in p["delays_ns"]]
            + [("shift_hz", f) for f in p["shifts_hz"]]
        }
        actual = [
            (r["candidate_id"], r["fs"], r["fine_step_hz"], r["grid"], r["case"], r["amount"])
            for r in rows
            if r["session_id"] == scan["session_id"]
        ]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("missing or duplicate frozen case")
    baseline = {
        (r["candidate_id"], r["fs"], r["fine_step_hz"], r["grid"]): r
        for r in rows
        if r["case"] == "baseline"
    }
    for row in rows:
        if row["case"] == "baseline":
            continue
        base = baseline[row["candidate_id"], row["fs"], row["fine_step_hz"], row["grid"]]
        a, b = row["target"], base["target"]
        detail = {
            k: row[k]
            for k in ("session_id", "candidate_id", "fs", "fine_step_hz", "grid", "case", "amount")
        }
        detail["recovered"] = a is not None and b is not None
        if detail["recovered"]:
            dt = timing_difference(a["epoch_s"], b["epoch_s"]) * 1e9
            df = a["cfo_hz"] - b["cfo_hz"]
            detail.update(
                timing_error_ns=dt - (row["amount"] if row["case"] == "delay_ns" else 0),
                cfo_error_hz=alias_difference(
                    df - (row["amount"] if row["case"] == "shift_hz" else 0)
                ),
                raw_cfo_delta_hz=df,
            )
        details.append(detail)
    summary = []
    for fs in plan["sample_rates_hz"]:
        for fine in plan["fine_steps_hz"]:
            for grid in plan["grids"]:
                for kind, key in (("delay_ns", "timing_error_ns"), ("shift_hz", "cfo_error_hz")):
                    group = [
                        r
                        for r in details
                        if (r["fs"], r["fine_step_hz"], r["grid"], r["case"])
                        == (fs, fine, grid, kind)
                    ]
                    good = [r for r in group if r["recovered"]]
                    paired_keys = set.intersection(
                        *[
                            {
                                (r["candidate_id"], r["amount"])
                                for r in details
                                if r["fs"] == rate
                                and r["fine_step_hz"] == fine
                                and r["grid"] == grid
                                and r["case"] == kind
                                and r["recovered"]
                            }
                            for rate in plan["sample_rates_hz"]
                        ]
                    )
                    shared = [r for r in good if (r["candidate_id"], r["amount"]) in paired_keys]
                    summary.append(
                        {
                            "fs": fs,
                            "fine_step_hz": fine,
                            "grid": grid,
                            "case": kind,
                            "attempted": len(group),
                            "recovered": len(good),
                            "paired_comparisons": len(shared),
                            "paired_rms_error": rms([r[key] for r in shared]) if shared else None,
                            "rms_error": rms([r[key] for r in good]) if good else None,
                            "p95_abs_error": float(np.quantile([abs(r[key]) for r in good], 0.95))
                            if good
                            else None,
                        }
                    )
    paired_ratios = []
    for fine in plan["fine_steps_hz"]:
        for grid in plan["grids"]:
            for kind, key in (("delay_ns", "timing_error_ns"), ("shift_hz", "cfo_error_hz")):
                by_rate = {
                    fs: {
                        (r["candidate_id"], r["amount"]): r
                        for r in details
                        if (r["fs"], r["fine_step_hz"], r["grid"], r["case"])
                        == (fs, fine, grid, kind)
                        and r["recovered"]
                    }
                    for fs in plan["sample_rates_hz"]
                }
                common = set.intersection(*(set(g) for g in by_rate.values()))
                pairs = []
                for scan in plan["selection"]:
                    keys = [
                        k for k in common if by_rate[5000000][k]["session_id"] == scan["session_id"]
                    ]
                    if keys:
                        pairs.append(
                            (
                                scan["session_id"],
                                rms([by_rate[5000000][k][key] for k in keys]),
                                rms([by_rate[2500000][k][key] for k in keys]),
                            )
                        )
                paired_ratios.append(
                    {
                        "fine_step_hz": fine,
                        "grid": grid,
                        "case": kind,
                        "five_over_two_point_five_ratio": bootstrap_scan_ratio(pairs),
                        "per_scan_rms": pairs,
                    }
                )
    write_json(
        args.output / "paired-summary.json",
        {
            "summary": summary,
            "paired_ratios": paired_ratios,
            "details": details,
            "baseline": list(baseline.values()),
            "limits": plan["limits"],
        },
    )
    with (args.output / "paired-summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    settings = [(fine, grid) for fine in plan["fine_steps_hz"] for grid in plan["grids"]]
    labels = [f"{fine} Hz / {grid}" for fine, grid in settings]
    for ax, kind, ylabel in zip(
        axes,
        ("delay_ns", "shift_hz"),
        ("Delay-recovery error RMS (ns)", "CFO-shift recovery error RMS (Hz)"),
        strict=True,
    ):
        for fs, delta, label in (
            (2500000, -0.18, "2.5 Msps, filtered/decimated"),
            (5000000, 0.18, "5 Msps, native"),
        ):
            values = [
                next(
                    r["paired_rms_error"]
                    for r in summary
                    if (r["fs"], r["fine_step_hz"], r["grid"], r["case"]) == (fs, fine, grid, kind)
                )
                for fine, grid in settings
            ]
            ax.bar(np.arange(len(settings)) + delta, values, width=0.36, label=label)
        ax.set_xticks(np.arange(len(settings)), labels)
        ax.set_xlabel("Acquisition fine step / GLRT points (conditioned step 100 Hz)")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.2)
    for ax, kind in zip(axes, ("delay_ns", "shift_hz"), strict=True):
        counts = sorted({r["paired_comparisons"] for r in summary if r["case"] == kind})
        attempts = sorted({r["attempted"] for r in summary if r["case"] == kind})
        ax.set_title(f"Paired cases {counts}; attempted per rate {attempts}")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.94), ncol=2, fontsize=9)
    fig.suptitle("Same historical IQ · 18 probes · fresh acquisition · shared recoveries only")
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(args.output / "paired-rate-comparison.png", dpi=170)
    plt.close(fig)
    for row in summary:
        print(json.dumps(row))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("reports/2026_09_10_historic_glrt_joint")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("plan", "replay", "summarize"), required=True)
    parser.add_argument("--max-seconds", type=float, default=600)
    args = parser.parse_args()
    path = args.output / "plan.json"
    if args.mode == "plan":
        if path.exists():
            raise ValueError("plan already exists; use a new output directory")
        write_json(path, make_plan(args.source))
    else:
        plan = json.loads(path.read_text())
        replay(args, plan) if args.mode == "replay" else summarize(args, plan)


if __name__ == "__main__":
    main()
