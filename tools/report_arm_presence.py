#!/usr/bin/env python3
"""Render descriptive held-out detector results; no RF or archive access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

GATE = 0.025
METHODS = {
    "lag_first20": "Periodicity · first 20 ms",
    "lag_spread60": "Periodicity · 3 × 20 ms",
    "lag_full120": "Periodicity · full 120 ms",
    "pss_first20": "PSS bank · first 20 ms",
    "pss_spread60": "PSS bank · 3 × 20 ms",
    "pss_full120": "PSS bank · full 120 ms",
    "cold2": "Fresh GLRT · 2 basins · 20 ms",
    "hybrid": "Causal cache + fresh fallback · 20 ms",
    "fresh8_first": "Reference GLRT · 8 basins · 20 ms",
    "fresh8_two": "Reference GLRT · first + last 20 ms",
    "fresh8_three": "Reference GLRT · 0 / 40 / 100 ms",
}


def load_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def reference_hit(row, indexes=range(6)):
    return any(
        c["margin"] >= GATE
        for rx in row["receivers"]
        for index in indexes
        for c in rx["reference"]["windows"][index]
    )


def repeated(row):
    return any(rx["reference"]["label"] == "repeated_reference_positive" for rx in row["receivers"])


def window_indexes(method):
    return {"fresh8_first": (0,), "fresh8_two": (0, 5), "fresh8_three": (0, 2, 5)}[method]


def detected(row, method, thresholds):
    if method.startswith("fresh8"):
        return reference_hit(row, window_indexes(method))
    if method in ("cold2", "hybrid"):
        return any(
            rx[method]["candidate"] is not None and rx[method]["candidate"]["margin"] >= GATE
            for rx in row["receivers"]
        )
    return any(
        rx["scouts"][method]["score"] > thresholds[str(row["rate_hz"])][method]
        for rx in row["receivers"]
    )


def cost(row, method, axis="cpu_ms"):
    conversion = row["ci16_to_complex"][axis]
    if method.startswith("fresh8"):
        return conversion + sum(
            rx["reference"]["window_times"][index][axis]
            for rx in row["receivers"]
            for index in window_indexes(method)
        )
    if method in ("cold2", "hybrid"):
        return conversion + sum(rx[method][axis] for rx in row["receivers"])
    return conversion + sum(rx["scouts"][method][axis] for rx in row["receivers"])


def control_hit(row, method, thresholds):
    if method == "cold2":
        return any(
            rx["cold2"]["margin"] is not None and rx["cold2"]["margin"] >= GATE
            for rx in row["receivers"]
        )
    if method in ("hybrid", "fresh8_first", "fresh8_two", "fresh8_three"):
        return None
    return detected(row, method, thresholds)


def distribution(values):
    return {
        "count": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(np.max(values)),
    }


def queue_delays(rows, method, factor):
    finish, delays = 0.0, []
    start = rows[0]["device_counter"]
    for row in rows:
        arrival = (row["device_counter"] - start) / row["rate_hz"] * 1000
        delays.append(max(0.0, finish - arrival))
        finish = max(arrival, finish) + factor * cost(row, method)
    return distribution(delays)


def summarize(rows, controls, thresholds):
    summary = {}
    for rate in (2_500_000, 5_000_000):
        selected = [row for row in rows if row["rate_hz"] == rate]
        positives = [row for row in selected if repeated(row)]
        any_positives = [row for row in selected if reference_hit(row)]
        negatives = [row for row in controls if row["rate_hz"] == rate]
        methods = {}
        for method in METHODS:
            hits = sum(detected(row, method, thresholds) for row in positives)
            false = [control_hit(row, method, thresholds) for row in negatives]
            methods[method] = {
                "repeated_reference_hits": hits,
                "repeated_reference_denominator": len(positives),
                "reference_recall_pct": 100 * hits / len(positives) if positives else None,
                "any_reference_hits": sum(
                    detected(row, method, thresholds) for row in any_positives
                ),
                "synthetic_control_alarms": None if any(x is None for x in false) else sum(false),
                "synthetic_control_count": len(negatives),
                "cpu_ms_dual_rx": distribution([cost(row, method) for row in selected]),
                "wall_ms_dual_rx": distribution([cost(row, method, "wall_ms") for row in selected]),
                "queue_wait_ms_scenarios": {
                    str(f): queue_delays(selected, method, f) for f in (1, 5, 10, 20)
                },
            }
        seeded = [rx for row in selected for rx in row["receivers"] if rx["cached"]["had_seed"]]
        seed_positive = [
            rx for rx in seeded if any(c["margin"] >= GATE for c in rx["reference"]["windows"][0])
        ]
        summary[str(rate)] = {
            "visits": len(selected),
            "repeated_reference_positive": len(positives),
            "any_reference_positive": len(any_positives),
            "single_only": len(any_positives) - len(positives),
            "unresolved": len(selected) - len(any_positives),
            "late_only_reference_visits": sum(
                not reference_hit(row, (0,)) for row in any_positives
            ),
            "methods": methods,
            "seeded_receiver_probes": len(seeded),
            "seeded_reference_positive_probes": len(seed_positive),
            "seeded_reference_positive_hits": sum(
                rx["cached"]["candidate"] is not None
                and rx["cached"]["candidate"]["margin"] >= GATE
                for rx in seed_positive
            ),
            "cached_cpu_ms_per_seeded_rx": distribution([rx["cached"]["cpu_ms"] for rx in seeded])
            if seeded
            else None,
            "hybrid_cold_fraction": float(
                np.mean([rx["hybrid"]["used_cold"] for row in selected for rx in row["receivers"]])
            ),
            "read_decompress_ms_per_visit": distribution(
                [row["read_and_decompress"]["wall_ms"] for row in selected]
            ),
            "conversion_cpu_ms_dual_rx": distribution(
                [row["ci16_to_complex"]["cpu_ms"] for row in selected]
            ),
        }
    return summary


def figures(output, rows, controls, thresholds, summary):
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    names = list(METHODS)
    colors = [
        "#4b8f8c" if name.startswith("lag") else "#d59840" if name.startswith("pss") else "#517bad"
        for name in names
    ]
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), gridspec_kw={"width_ratios": [1.25, 1]})
    for row_index, rate in enumerate((2_500_000, 5_000_000)):
        group = summary[str(rate)]
        measures = [group["methods"][name] for name in names]
        left, right = axes[row_index]
        y = np.arange(len(names))
        enough_positives = group["repeated_reference_positive"] >= 10
        display = [
            item["reference_recall_pct"] if enough_positives else item["repeated_reference_hits"]
            for item in measures
        ]
        left.barh(y, display, color=colors if enough_positives else "#aaaaaa")
        left.set_yticks(y, [METHODS[name] for name in names])
        left.set_xlim(0, 110 if enough_positives else 1.15)
        left.invert_yaxis()
        left.set_title(
            f"{rate / 1e6:g} MS/s · {group['repeated_reference_positive']} repeated-positive visits"
        )
        left.set_xlabel(
            "Held-out reference-positive visits flagged (%)"
            if enough_positives
            else "Observed hits among ONE positive visit — insufficient to estimate sensitivity"
        )
        for index, item in enumerate(measures):
            left.text(
                display[index] + (1 if enough_positives else 0.02),
                index,
                f"{item['repeated_reference_hits']}/{item['repeated_reference_denominator']}",
                va="center",
                fontsize=8,
            )
        median = [item["cpu_ms_dual_rx"]["median"] for item in measures]
        p95 = [item["cpu_ms_dual_rx"]["p95"] for item in measures]
        right.hlines(y, median, p95, color=colors, linewidth=3, alpha=0.6)
        right.scatter(median, y, color=colors, label="median", zorder=3)
        right.scatter(p95, y, color=colors, marker="|", s=100, label="p95", zorder=3)
        right.set_xscale("log")
        right.set_yticks(y, [])
        right.invert_yaxis()
        right.set_xlabel("Desktop CPU ms per dual-RX visit (log scale)")
        right.set_title("Includes conversion; excludes archive I/O")
        right.grid(axis="x", alpha=0.2)
        right.legend(loc="lower right")
    fig.suptitle(
        "Lightweight detector screening: sensitivity and total desktop compute\n"
        "Reference agreement, not verified Starlink recall; these are not ARM timings",
        fontsize=15,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output / "01-quality-versus-cost.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(14, 7))
    for ax, rate in zip(axes, (2_500_000, 5_000_000), strict=True):
        selected = [row for row in rows if row["rate_hz"] == rate]
        grid = np.full((8, 48), np.nan)
        for row in selected:
            sweep = row["visit_index"] // 8 - 150
            for window in range(6):
                grid[row["target_index"], sweep * 6 + window] = max(
                    (
                        c["margin"]
                        for rx in row["receivers"]
                        for c in rx["reference"]["windows"][window]
                    ),
                    default=0.0,
                )
        im = ax.imshow(
            grid, aspect="auto", vmin=0, vmax=0.12, cmap="viridis", interpolation="nearest"
        )
        for x in np.arange(0.5, 48, 6):
            ax.axvline(x, color="white", alpha=0.6, lw=0.7)
        ax.set_yticks(range(8), [f"CH{ch}{edge}" for edge in ("L", "U") for ch in range(1, 5)])
        ax.set_xticks(np.arange(2.5, 48, 6), [str(i) for i in range(1, 9)])
        ax.set_xlabel("Revisit number · six cells per visit = 0–20, 20–40, …, 100–120 ms")
        ax.set_title(
            f"{rate / 1e6:g} MS/s · {selected[0]['session_id']} · best fractional margin across RX"
        )
        fig.colorbar(im, ax=ax, label="Fractional GLRT margin (gate 0.025)", pad=0.02)
    fig.suptitle(
        "Why inspect the whole visit? Signal evidence changes within 120 ms\n"
        "White line marks the end of each visit's first 20 ms; retune gaps are not to scale",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(output / "02-within-visit-coverage.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for i, rate in enumerate((2_500_000, 5_000_000)):
        positive = [row for row in rows if row["rate_hz"] == rate and repeated(row)]
        negative = [row for row in controls if row["rate_hz"] == rate]
        for j, method in enumerate(("lag_full120", "pss_full120")):
            ax = axes[i, j]
            for category, selected, color in (
                (
                    "Gaussian control",
                    [row for row in negative if row["kind"] == "gaussian"],
                    "#999999",
                ),
                (
                    "Tone + noise control",
                    [row for row in negative if row["kind"] == "tone_noise"],
                    "#cc805a",
                ),
                ("Repeated GLRT-positive IQ", positive, "#517bad"),
            ):
                scores = sorted(
                    max(rx["scouts"][method]["score"] for rx in row["receivers"])
                    for row in selected
                )
                if scores:
                    ax.step(
                        scores,
                        np.arange(1, len(scores) + 1) / len(scores),
                        where="post",
                        label=f"{category} (n={len(scores)})",
                        color=color,
                    )
            ax.axvline(
                thresholds[str(rate)][method],
                color="black",
                linestyle="--",
                label="Frozen development threshold",
            )
            ax.set_title(f"{rate / 1e6:g} MS/s · {METHODS[method]}")
            ax.set_xlabel("Dual-RX maximum scout score")
            ax.set_ylabel("Cumulative fraction")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.15)
    fig.suptitle(
        "Specificity check: are scout scores distinguishable from controls?\n"
        "Synthetic controls only; real-interference false-alarm rates remain unknown",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(output / "03-control-separation.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    selected_methods = ("lag_full120", "pss_first20", "cold2", "hybrid")
    for ax, rate in zip(axes, (2_500_000, 5_000_000), strict=True):
        for method in selected_methods:
            p95 = summary[str(rate)]["methods"][method]["cpu_ms_dual_rx"]["p95"]
            ax.plot([1, 5, 10, 20], p95 * np.array([1, 5, 10, 20]), "o-", label=METHODS[method])
        ax.axhline(20, color="black", linestyle="--", label="Provisional 20 ms ARM CPU budget")
        ax.set_yscale("log")
        ax.set_xticks([1, 5, 10, 20])
        ax.set_title(f"{rate / 1e6:g} MS/s · p95 compute")
        ax.set_xlabel("Assumed slowdown relative to desktop")
        ax.set_ylabel("Projected CPU ms per dual-RX visit")
        ax.grid(alpha=0.15)
    axes[1].legend(fontsize=8, loc="upper left")
    fig.suptitle("ARM sensitivity scenarios — NOT calibrated processor ratios", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(output / "04-arm-budget-scenarios.png", dpi=160)
    plt.close(fig)

    tone_path = output / "tone-reference-check.json"
    if tone_path.exists():
        cases = json.loads(tone_path.read_text())["rows"]
        fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
        for i, rate in enumerate((2_500_000, 5_000_000)):
            for j, edge in enumerate(("lower", "upper")):
                ax = axes[i, j]
                for case in cases:
                    if case["rate_hz"] != rate or case["edge"] != edge:
                        continue
                    scores = [
                        max((c["margin"] for c in window), default=0.0)
                        for window in case["windows"]
                    ]
                    ax.plot(
                        np.arange(6) * 20 + 10,
                        scores,
                        "o-",
                        label=case["kind"] + " · " + case["label"].replace("_", " "),
                    )
                ax.axhline(GATE, color="black", linestyle="--", label="Existing margin gate")
                ax.set_title(f"{rate / 1e6:g} MS/s · {edge} edge")
                ax.set_xlabel("Window midpoint in synthetic block (ms)")
                ax.set_ylabel("Best eight-basin fractional GLRT margin")
                ax.legend(fontsize=7)
                ax.grid(alpha=0.15)
        fig.suptitle(
            "Counterexample: a constant tone can satisfy the GLRT reference label\n"
            "No Starlink waveform is present; tone amplitude 6 + complex Gaussian noise",
            fontsize=14,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.9))
        fig.savefig(output / "05-tone-counterexample.png", dpi=160)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output
    thresholds = json.loads((output / "thresholds.json").read_text())["thresholds"]
    results = {}
    for split in ("develop", "heldout"):
        rows = load_rows(output / f"{split}-visits.jsonl")
        controls = load_rows(output / f"{split}-controls.jsonl")
        results[split] = summarize(rows, controls, thresholds)
    (output / "summary.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    figures(output, rows, controls, thresholds, results["heldout"])
    for rate, group in results["heldout"].items():
        print(
            rate,
            "repeated positives",
            group["repeated_reference_positive"],
            "late-only",
            group["late_only_reference_visits"],
            "cold fraction",
            round(group["hybrid_cold_fraction"], 3),
        )
        for name, value in group["methods"].items():
            print(
                name,
                f"{value['repeated_reference_hits']}/{value['repeated_reference_denominator']}",
                "CPU median/p95",
                round(value["cpu_ms_dual_rx"]["median"], 2),
                round(value["cpu_ms_dual_rx"]["p95"], 2),
                "synthetic alarms",
                value["synthetic_control_alarms"],
            )


if __name__ == "__main__":
    main()
