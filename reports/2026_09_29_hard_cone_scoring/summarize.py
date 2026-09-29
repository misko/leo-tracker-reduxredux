"""Audit the stored gate scores and compare identical held observations."""
# ruff: noqa: E501 -- Generated Markdown prose and tables.

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import HERE, bind, read, save, verify


def main():
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]
    rows, unique, receipts, highlights = [], [], [], []
    target_ids = {
        "sha256:a9563aec999b3232981a7edc46ea49be0b07860f9968a969068db297b22155e0",
        "sha256:4261f7784675acae1a36574039d74840f7f822b73fcd9668ab22846d7ed8ea86",
    }
    for unit in plan["units"]:
        folder = HERE / "runs" / unit["unit_id"]
        for name, value in read(folder / "seal.json")["sha256"].items():
            assert name not in bindings or bindings[name] == value
            bindings[name] = value
        assert int((folder / "exit-code.txt").read_text()) == 0
        result = read(folder / "result.json")
        assert (
            result["audit_passed"]
            and result["replay_passed"]
            and result["unit_id"] == unit["unit_id"]
        )
        assert result["unchanged_position_timings"] == unit["x"]
        assert set(result["models"]) == {"baseline", *plan["arms"]}
        geometry = {(r["session_id"], r["track_id"]): r for r in result["geometry"]}
        baseline = {
            (r["session_id"], r["track_id"]): r for r in result["models"]["baseline"]["rows"]
        }
        assert len(geometry) == len(baseline) == unit["group"]["tracks"]
        base_held = sum(r["held_log_score"] for r in baseline.values())
        per_arm = {}
        for arm in plan["arms"]:
            model = result["models"][arm]
            assert {(r["session_id"], r["track_id"]) for r in model["rows"]} == baseline.keys()
            width = int(arm[-2:])
            unsupported, changed, comparable = [], 0, 0
            for r in model["rows"]:
                key = r["session_id"], r["track_id"]
                g = geometry[key]
                train, held, visible = (
                    np.array(g["training_max_angles_deg"]),
                    np.array(g["held_max_angles_deg"]),
                    np.array(g["horizon_visible"], dtype=bool),
                )
                weights = np.array(r["candidate_responsibilities"])
                supported = visible & (train <= width)
                assert len(weights) == len(train) == len(visible)
                assert visible.any() and np.isfinite(weights).all() and np.all(weights >= 0)
                assert abs(weights.sum() + r["background_responsibility"] - 1) < 1e-10
                assert abs(weights.sum() - r["signal_responsibility"]) < 1e-10
                assert r["hard_supported_candidates"] == int(supported.sum())
                assert (
                    abs(float(weights @ (train <= width)) - r["training_inside_signal_mass"])
                    < 1e-10
                )
                assert (
                    abs(
                        float(weights @ ((train <= width) & (held <= width)))
                        - r["both_inside_signal_mass"]
                    )
                    < 1e-10
                )
                compatibility = (
                    (train <= width).astype(float)
                    if arm.startswith("hard")
                    else np.exp(-np.logaddexp(0, (train - width) / 2))
                )
                expected_bg = 0.2 + 0.8 * (1 - float(compatibility[visible].mean()))
                assert abs(expected_bg - r["background_prior_mass"]) < 1e-12
                assert r["held_observations"] == baseline[key]["held_observations"]
                if arm.startswith("hard"):
                    assert np.all(weights[~supported] == 0)
                    if not supported.any():
                        assert r["background_responsibility"] == 1
                if not supported.any():
                    unsupported.append(r["session_id"])
                if (
                    r["signal_responsibility"] > 0.5
                    and baseline[key]["signal_responsibility"] > 0.5
                ):
                    comparable += 1
                    changed += int(
                        np.argmax(weights) != np.argmax(baseline[key]["candidate_responsibilities"])
                    )
                if unit["group"]["size"] == 8:
                    unique.append({"dataset": unit["group"]["source_dataset"], "arm": arm, **r})
                    if r["track_id"] in target_ids:
                        highlights.append(
                            {
                                "unit": unit["unit_id"],
                                "arm": arm,
                                "track_id": r["track_id"],
                                "signal_responsibility": r["signal_responsibility"],
                                "held_change_nats": r["held_log_score"]
                                - baseline[key]["held_log_score"],
                            }
                        )
            assert abs(sum(r["training_log_score"] for r in model["rows"]) - model["score"]) < 1e-7
            held_total = sum(r["held_log_score"] for r in model["rows"])
            assert np.isfinite(held_total)
            per_arm[arm] = {
                "held_total": held_total,
                "held_change_nats": held_total - base_held,
                "unsupported_tracks": len(unsupported),
                "unsupported_scans": len(set(unsupported)),
                "dominant_changes": changed,
                "comparable_signal_tracks": comparable,
            }
        rows.append(
            {
                "unit": unit["unit_id"],
                "dataset": unit["group"]["source_dataset"],
                "size": unit["group"]["size"],
                "baseline_held_total": base_held,
                "arms": per_arm,
            }
        )
        resource = (folder / "resources.txt").read_text()
        elapsed = next(
            s.rsplit(": ", 1)[1] for s in resource.splitlines() if "Elapsed (wall clock)" in s
        )
        seconds = 0.0
        for part in elapsed.split(":"):
            seconds = seconds * 60 + float(part)
        rss = int(
            next(
                s.rsplit(":", 1)[1]
                for s in resource.splitlines()
                if "Maximum resident set size" in s
            )
        )
        assert "Exit status: 0" in resource
        receipts.append({"unit": unit["unit_id"], "wall_seconds": seconds, "peak_rss_kib": rss})
    verify(bindings)
    assert len(rows) == len(receipts) == 18 and len(highlights) == 8
    aggregates = []
    for arm in plan["arms"]:
        records = [r for r in unique if r["arm"] == arm]
        assert len(records) == len({(r["session_id"], r["track_id"]) for r in records}) == 4328
        assert len({r["session_id"] for r in records}) == 72
        rho = sum(r["signal_responsibility"] for r in records)
        unsupported = [r for r in records if r["hard_supported_candidates"] == 0]
        delta = [r["arms"][arm]["held_change_nats"] for r in rows]
        aggregates.append(
            {
                "arm": arm,
                "panels_better_than_no_cone": sum(v > 0 for v in delta),
                "median_held_change_nats": float(np.median(delta)),
                "min_held_change_nats": min(delta),
                "max_held_change_nats": max(delta),
                "unsupported_tracks": len(unsupported),
                "unsupported_scans": len({r["session_id"] for r in unsupported}),
                "signal_weight": rho,
                "background_weight": sum(r["background_responsibility"] for r in records),
                "training_inside_fraction": sum(r["training_inside_signal_mass"] for r in records)
                / rho
                if rho
                else None,
                "both_inside_fraction": sum(r["both_inside_signal_mass"] for r in records) / rho
                if rho
                else None,
            }
        )
    paired = []
    for width in (40, 50):
        delta = [
            r["arms"][f"hard{width}"]["held_total"] - r["arms"][f"soft{width}"]["held_total"]
            for r in rows
        ]
        paired.append(
            {
                "half_angle_deg": width,
                "hard_better_panels": sum(d > 0 for d in delta),
                "median_hard_minus_soft_nats": float(np.median(delta)),
                "changes": delta,
            }
        )
    save(
        HERE / "summary.json",
        {
            "rows": rows,
            "aggregates": aggregates,
            "hard_vs_soft": paired,
            "targets": highlights,
            "resources": receipts,
        },
    )
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
    for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
        subset = [r for r in rows if r["dataset"] == ds]
        for arm in plan["arms"]:
            ax.plot(
                range(6),
                [r["arms"][arm]["held_change_nats"] for r in subset],
                "o-" if arm.startswith("hard") else "s--",
                label=arm,
            )
        ax.axhline(0, color="gray", linewidth=1)
        ax.set_xticks(
            range(6), [r["unit"].split("_")[1][0].upper() + str(r["size"]) for r in subset]
        )
        ax.set_title(ds)
        ax.set_xlabel("Early / middle / late; scans per set")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Held log-score change vs no cone (nats)")
    axes[0].legend()
    fig.suptitle("Hard/soft gates at identical fixed fits; no new location estimates")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"held-comparison.{suffix}", dpi=160)
    plt.close(fig)
    lines = [
        "# Hard versus soft cones at unchanged fitted locations",
        "",
        "All eighteen fixed-position panels completed and replay the published no-cone q=0.20 model. "
        "This experiment changes only training-cone weights and their transfer to the unassociated trend. "
        "Location, per-scan timing, candidate banks and held observations remain identical. "
        "It produces no new geographic accuracy estimate.",
        "",
        "| Arm | Better held prediction vs no cone | Median change (nats) | Range (nats) | Unsupported tracks / 4,328 | Scans with unsupported tracks / 72 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in aggregates:
        lines.append(
            f"| {r['arm']} | {r['panels_better_than_no_cone']}/18 | {r['median_held_change_nats']:+.3f} | {r['min_held_change_nats']:+.3f} to {r['max_held_change_nats']:+.3f} | {r['unsupported_tracks']} | {r['unsupported_scans']} |"
        )
    lines += [
        "",
        "Unsupported means no retained training-horizon-visible candidate stays inside the width throughout training. "
        "Counts use only nine nonoverlapping eight-scan sets. The soft arm may retain outside-cone signal weight; "
        "the hard arm assigns unsupported tracks entirely to background. Background is not a complete satellite explanation.",
        "",
        "| Half-angle | Hard beats soft held score | Median hard-minus-soft (nats) |",
        "|---|---:|---:|",
    ]
    for r in paired:
        lines.append(
            f"| {r['half_angle_deg']}° | {r['hard_better_panels']}/18 | {r['median_hard_minus_soft_nats']:+.3f} |"
        )
    lines += [
        "",
        "![Matched held comparison](held-comparison.png)",
        "",
        "## Every panel",
        "",
        "| Panel | soft40 − baseline | hard40 − baseline | soft50 − baseline | hard50 − baseline |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['unit']} | "
            + " | ".join(f"{r['arms'][a]['held_change_nats']:+.3f}" for a in plan["arms"])
            + " |"
        )
    lines += [
        "",
        "## Geometry and limitations",
        "",
        "| Arm | Training-inside / satellite weight | Training-and-held-inside / satellite weight |",
        "|---|---:|---:|",
    ]
    for r in aggregates:
        a = (
            f"{100 * r['training_inside_fraction']:.2f}%"
            if r["training_inside_fraction"] is not None
            else "Undefined"
        )
        b = (
            f"{100 * r['both_inside_fraction']:.2f}%"
            if r["both_inside_fraction"] is not None
            else "Undefined"
        )
        lines.append(f"| {r['arm']} | {a} | {b} |")
    lines += [
        "",
        "Hard gates enforce training consistency for signal hypotheses; held geometry remains diagnostic. "
        "The normalized conditional frequency score does not model observing opportunities or non-detections "
        "and does not enforce hard visibility at held times. No receiver orientation or travel direction is calibrated. "
        "Counts across nested panels are dependent, and the retained banks are not the full catalogue.",
        "",
        "The complete results retain reassociation counts among tracks with signal responsibility >0.5 in the scored arm and no-cone baseline, "
        "with explicit denominators, and the two previously excluded RX0 tracks. Posterior concentration is not verified identity. "
        "Any subsequent hard-gate position fit requires separate tests and a bounded search for a discontinuous objective.",
        "",
        f"All 18 child processes exit zero; summed wall time {sum(r['wall_seconds'] for r in receipts):.2f} s, "
        f"maximum {max(r['wall_seconds'] for r in receipts):.2f} s, peak RSS {max(r['peak_rss_kib'] for r in receipts):,} KiB. "
        "Frozen execution/input hashes, baseline replays, observation identities, probability sums, exact hard zeros and support masses were verified. "
        "No new fits, RF, raw IQ, propagation, provider fetches or archive reads.",
        "",
        "[Protocol](PROTOCOL.md), [nine passing prelaunch tests](tests-fixed-imports.log), "
        "[initial import failure](tests.log), [complete results](summary.json), [evidence hashes](evidence-sha256.json).",
        "",
    ]
    with (HERE / "README.md").open("x") as f:
        f.write("\n".join(lines))
    bindings.update(
        bind(p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    )
    save(HERE / "evidence-sha256.json", {"sha256": bindings})
    print({"panels": len(rows), "arms": aggregates, "hard_vs_soft": paired}, flush=True)


if __name__ == "__main__":
    main()
