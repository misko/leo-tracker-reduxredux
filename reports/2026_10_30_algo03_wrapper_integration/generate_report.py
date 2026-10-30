"""Reproduce evaluation-only tables and figure from the archived wrapper terminal."""

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
TRUTH = (37.849061591561885, -122.48574968092912)


def distance(position):
    lat, lon, lat0, lon0 = map(math.radians, (*position, *TRUTH))
    a = math.sin((lat - lat0) / 2) ** 2
    a += math.cos(lat) * math.cos(lat0) * math.sin((lon - lon0) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def main():
    sources = json.loads((ROOT / "sources.json").read_text())
    for name, expected in sources["archived_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    terminal = json.loads((ROOT / "evidence/terminal.json").read_text())
    assert terminal["state"] == "complete" and terminal["decision"] == "ALGO03_joint"
    assert all(terminal["rf_checks"].values())
    receipts = [json.loads(p.read_text())
                for p in (ROOT / "evidence/read_receipts").glob("*.json")]
    observed = {r["pid"] for r in receipts}
    roots = [r for r in receipts if r["parent_pid"] not in observed]
    assert len(roots) == 1
    assert len(receipts) == len(observed) == 1 + sum(len(r["python_spawns"]) for r in receipts)
    assert not any(r["denied_paths"] for r in receipts)
    supervisor = roots[0]["parent_pid"]
    assert all(r["parent_pid"] in observed | {supervisor} for r in receipts)
    rows = []
    targets = {o for t in terminal["selected"]["targets"] for o in t["observation_ids"]}
    for arm in ("c0", "fitted_c"):
        before = terminal["baseline"]["arms"][arm]
        after = terminal["selected"]["arms"][arm]
        old = {o for t in before["gates"]["tracks"] + before.get("linear_gates", [])
               for o in t["observation_ids"]}
        new = set(after["associated_ids"])
        assert new == old | targets and not old & targets
        total = sources["inventory_summary"][arm]["total_GLRT"]
        rows.append(dict(arm=arm, before_error_km=distance(before["endpoint_latlon"]),
                         after_error_km=distance(after["endpoint_latlon"]),
                         before_associated=len(old), after_associated=len(new), total_GLRT=total,
                         before_percent=100 * len(old) / total,
                         after_percent=100 * len(new) / total,
                         before_negative_twice_elbo=before["negative_twice_elbo"],
                         after_negative_twice_elbo=after["negative_twice_elbo"],
                         baseline_frequency_RMS_hz=before["RMS_hz"],
                         selected_frequency_RMS_hz=None))
    arms = terminal["selected"]["arms"]
    assert arms["c0"]["associated_ids"] == arms["fitted_c"]["associated_ids"]
    summary = dict(evaluation_only_latlon=TRUTH, inference_uses_truth=False,
                   full_cohort_claim=False, production_activated=False,
                   source_revision_under_comparison="e67f67484c4f54316b33dfd8e12f6e68d09d1e13",
                   canary_predates_final_wrapper_metadata_fix=True,
                   job_id=sources["job_id"], input_sha256=terminal["input_sha256"],
                   decision=terminal["decision"], rows=rows,
                   baseline_seconds=terminal["baseline_seconds"],
                   recovery_seconds=terminal["recovery_seconds"],
                   total_seconds=terminal["total_seconds"], read_audit=terminal["read_audit"],
                   report_only_read_tree_replay=dict(verified=True, receipts=len(receipts),
                       reconstructed_root_process_id=roots[0]["pid"],
                       reconstructed_supervisor_process_id=supervisor,
                       original_terminal_modified=False),
                   recovered_targets=[{k: t[k] for k in ("component", "norad", "points")}
                                      for t in terminal["selected"]["targets"]])
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    with (ROOT / "results.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), layout="constrained")
    colors = ("#426a93", "#cf7441")
    x = np.arange(2)
    for offset, key, color, label in ((-.18, "before", colors[0], "ALGO02 baseline"),
                                     (.18, "after", colors[1], "ALGO03 joint recovery")):
        values = [r[key + "_error_km"] for r in rows]
        bars = axes[0].bar(x + offset, values, .36, color=color, label=label)
        axes[0].bar_label(bars, fmt="%.3f", fontsize=9, padding=3)
    axes[0].set(xticks=x, xticklabels=["c = 0", "Fitted c"], ylabel="Position error (km)",
                ylim=(0, 1.3), title="Accuracy: error increases in both arms")
    axes[0].legend(fontsize=8, loc="lower left")
    values = [rows[0][key + "_percent"] for key in ("before", "after")]
    bars = axes[1].bar(x, values, color=colors)
    axes[1].bar_label(bars, labels=[f"{v:.2f}%" for v in values], padding=3)
    axes[1].set(xticks=x, xticklabels=["ALGO02", "ALGO03"], ylim=(0, 100),
                ylabel="Original GLRT observations associated (%)",
                title="Support: 2,963 → 3,067 / 4,174")
    axes[1].text(.5, 7, "+104 scored observations · +2.49 percentage points",
                 ha="center", fontsize=8)
    baseline, recovery = terminal["baseline_seconds"], terminal["recovery_seconds"]
    axes[2].bar(0, baseline, color=colors[0], label="Original ALGO02")
    axes[2].bar(0, recovery, bottom=baseline, color=colors[1], label="Recovery")
    axes[2].text(0, baseline / 2, f"ALGO02\n{baseline:.1f} s",
                 ha="center", va="center", color="white")
    axes[2].text(0, baseline + recovery / 2, f"Recovery\n{recovery:.1f} s",
                 ha="center", va="center", color="white")
    axes[2].set(xticks=[0], xticklabels=[f"Combined: {baseline + recovery:.1f} s"],
                ylabel="Elapsed processing time (s)", ylim=(0, 1700),
                title="Runtime includes the original baseline")
    fig.suptitle("One wrapper integration canary — RF qualification does not guarantee "
                 "better localization", fontsize=12)
    (ROOT / "figures").mkdir(exist_ok=True)
    fig.savefig(ROOT / "figures/wrapper_comparison.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
