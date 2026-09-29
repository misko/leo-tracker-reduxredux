"""Keep original gate failures distinct from fine-step-reviewed predictive results."""

import hashlib
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for f in [
    HERE / "input-seal.json",
    *HERE.glob("runs/**/seal.json"),
    *HERE.glob("gradient-review/*/seal.json"),
]:
    for name, digest in json.loads(f.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
rows = []
for unit in plan["units"]:
    folder = HERE / "gradient-review" / unit["unit_id"]
    assert int((folder / "exit-code.txt").read_text()) == 0
    r = json.loads((folder / "result.json").read_text())
    selected = json.loads((HERE / "runs" / unit["unit_id"] / "selection.json").read_text())[
        "selected"
    ]
    assert r["position"] == unit["position"] and r["timings"] == selected["timings"]
    assert r["original_audit_exit_code"] == int(
        (HERE / "runs" / unit["unit_id"] / "held/exit-code.txt").read_text()
    )
    assert len(r["checks"]) == unit["size"]
    for check in r["checks"]:
        assert [s["step_s"] for s in check["steps"]] == [
            0.001,
            0.0005,
            0.00025,
            0.000125,
            0.0000625,
            0.00003125,
        ]
        fine = check["steps"][-2:]
        assert check["fine_step_pass"] == bool(
            all(not s["crosses_grid_node"] and s["absolute_difference"] < 0.002 for s in fine)
            and abs(fine[0]["numerical"] - fine[1]["numerical"]) < 0.002
        )
    original_pass = all(
        s["absolute_difference"] < 0.002 for c in r["checks"] for s in c["steps"][:2]
    )
    assert original_pass == (r["original_audit_exit_code"] == 0)
    assert r["fine_step_pass"] == all(c["fine_step_pass"] for c in r["checks"])
    row = {
        k: unit[k]
        for k in ("unit_id", "dataset", "block", "size", "source_receiver", "target_receiver")
    }
    row.update(
        original_pass=original_pass,
        fine_step_pass=r["fine_step_pass"],
        maximum_coarse_error=max(
            s["absolute_difference"] for c in r["checks"] for s in c["steps"][:2]
        ),
        maximum_fine_error=max(
            s["absolute_difference"] for c in r["checks"] for s in c["steps"][-2:]
        ),
    )
    if r["fine_step_pass"]:
        assert abs(r["training_log_score"] - selected["training_log_score"]) < 1e-7
        current = {(a["session_id"], a["track_id"]): a for a in r["rows"]}
        assert len(current) == len(r["rows"]) == unit["group"]["tracks"]
        assert set(current) == {
            (a["session_id"], t)
            for a in unit["group"]["receiver_partition"]
            for t in a["track_ids"]
        }
        prior = json.loads((ROOT / unit["prior_transfer"]).read_text())["other_receiver"]
        before = {(a["session_id"], a["track_id"]): a for a in prior["rows"]}
        both = {
            (a["session_id"], a["track_id"]): a
            for a in json.loads((ROOT / unit["both_audit"]).read_text())["rows"]
        }
        assert set(before) == set(current) < set(both)
        assert all(
            v["held_observations"] == before[k]["held_observations"] == both[k]["held_observations"]
            for k, v in current.items()
        )
        for field in ("training_log_score", "held_log_score"):
            assert abs(sum(a[field] for a in r["rows"]) - r[field]) < 1e-7
        baseline = sum(both[k]["held_log_score"] for k in current)
        original_loss = prior["held_log_score"] - baseline
        assert original_loss < 0
        gain = r["held_log_score"] - prior["held_log_score"]
        row.update(
            held_gain_from_timing_refit=gain,
            prior_held_change_vs_both=original_loss,
            refit_held_change_vs_both=r["held_log_score"] - baseline,
            fraction_prior_loss_recovered=gain / (-original_loss),
            training_gain=r["training_log_score"] - prior["training_log_score"],
            max_timing_change_s=max(
                abs(a - b) for a, b in zip(r["timings"], unit["starts"][0]["timings"], strict=True)
            ),
        )
    rows.append(row)
valid = [r for r in rows if r["fine_step_pass"]]
summary = {
    "units": rows,
    "planned": 36,
    "original_audit_passed": sum(r["original_pass"] for r in rows),
    "fine_step_passed": len(valid),
    "execution_bindings_verified": len(bindings),
    "held_improved_vs_transfer": sum(r["held_gain_from_timing_refit"] > 0 for r in valid),
    "held_improved_vs_both": sum(r["refit_held_change_vs_both"] > 0 for r in valid),
    "median_fraction_loss_recovered": float(
        np.median([r["fraction_prior_loss_recovered"] for r in valid])
    )
    if valid
    else None,
}
(HERE / "review-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
resources = []
for f in sorted(
    [*HERE.glob("runs/**/resources.txt"), *HERE.glob("gradient-review/*/resources.txt")]
):
    text = f.read_text()
    seconds = 0.0
    for part in re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1).split(":"):
        seconds = 60 * seconds + float(part)
    resources.append(
        {
            "job": str(f.parent.relative_to(HERE)),
            "wall_s": seconds,
            "exit_code": int((f.parent / "exit-code.txt").read_text()),
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
            ),
        }
    )
(HERE / "review-resources.json").write_text(
    json.dumps(
        {
            "jobs": resources,
            "total_job_wall_s": sum(r["wall_s"] for r in resources),
            "max_job_wall_s": max(r["wall_s"] for r in resources),
            "max_rss_kib": max(r["max_rss_kib"] for r in resources),
        },
        indent=2,
    )
    + "\n"
)
fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
for rx, color in (("0", "tab:orange"), ("1", "tab:blue")):
    for size, marker in ((4, "o"), (8, "s")):
        subset = [r for r in valid if r["source_receiver"] == rx and r["size"] == size]
        axes[0].scatter(
            [r["prior_held_change_vs_both"] for r in subset],
            [r["refit_held_change_vs_both"] for r in subset],
            color=color,
            marker=marker,
            label=f"RX{rx} source, {size} scans",
        )
        axes[1].scatter(
            [r["maximum_coarse_error"] for r in subset],
            [r["maximum_fine_error"] for r in subset],
            color=color,
            marker=marker,
        )
axes[0].axhline(0, color="black", linestyle="--")
axes[0].set(
    xlabel="Before timing refit: held change vs both (nats)",
    ylabel="After timing refit: held change vs both (nats)",
)
axes[0].legend()
axes[1].set(
    xscale="log",
    yscale="log",
    xlabel="Maximum original-step gradient discrepancy",
    ylabel="Maximum fine-step discrepancy",
)
axes[1].axvline(0.002, color="black", linestyle="--")
axes[1].axhline(0.002, color="black", linestyle="--")
fig.suptitle("Fixed source positions · separate fine-step review · original failures retained")
fig.savefig(HERE / "review.png", dpi=170)
fig.savefig(HERE / "review.svg")
print(json.dumps({k: v for k, v in summary.items() if k != "units"}, indent=2))
