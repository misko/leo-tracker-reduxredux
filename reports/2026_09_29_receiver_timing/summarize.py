"""Audit fixed-position timing fits and matched predictive recovery."""

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
for path in [HERE / "input-seal.json", *HERE.glob("runs/**/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
rows, resources = [], []
for unit in plan["units"]:
    parent = HERE / "runs" / unit["unit_id"]
    selection = json.loads((parent / "selection.json").read_text())
    assert [r["start"] for r in selection["runs"]] == [s["label"] for s in unit["starts"]]
    eligible = []
    for run in selection["runs"]:
        folder = parent / "fit" / run["start"]
        assert run["exit_code"] == int((folder / "exit-code.txt").read_text())
        fit = run["result"]
        if fit is None:
            assert run["exit_code"] != 0
            continue
        assert fit == json.loads((folder / "result.json").read_text())
        assert fit["position"] == unit["position"]
        assert fit["initial"] == next(
            s["timings"] for s in unit["starts"] if s["label"] == run["start"]
        )
        assert fit["session_ids"] == unit["group"]["session_ids"]
        assert fit["target_receiver"] == unit["target_receiver"]
        boundary = any(abs(t) > 4.999 for t in fit["timings"])
        assert fit["qualified"] == bool(
            fit["success"] and not boundary and max(map(abs, fit["gradient"])) <= 0.01
        )
        if fit["qualified"]:
            eligible.append(fit)
    chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selection["selected"] == chosen and selection["qualified_starts"] == len(eligible)
    row = {
        k: unit[k]
        for k in (
            "unit_id",
            "dataset",
            "block",
            "size",
            "source_receiver",
            "target_receiver",
            "position",
        )
    }
    row.update(qualified_starts=len(eligible), selected=chosen, validated=False)
    if chosen is not None:
        held_path = parent / "held"
        code = int((held_path / "exit-code.txt").read_text())
        row["audit_exit_code"] = code
        if code == 0:
            held = json.loads((held_path / "result.json").read_text())
            assert held["position"] == unit["position"] and held["timings"] == chosen["timings"]
            assert len(held["timing_gradient_checks"]) == 2 * unit["size"]
            assert max(c["absolute_difference"] for c in held["timing_gradient_checks"]) < 0.002
            assert abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
            for field in ("training_log_score", "held_log_score"):
                assert abs(sum(r[field] for r in held["rows"]) - held[field]) < 1e-7
            before = json.loads((ROOT / unit["prior_transfer"]).read_text())["other_receiver"]
            assert before["position_and_timings"][:2] == unit["position"]
            assert before["position_and_timings"][2:] == unit["starts"][0]["timings"]
            baseline = json.loads((ROOT / unit["both_audit"]).read_text())
            current = {(r["session_id"], r["track_id"]): r for r in held["rows"]}
            transferred = {(r["session_id"], r["track_id"]): r for r in before["rows"]}
            both = {(r["session_id"], r["track_id"]): r for r in baseline["rows"]}
            assert len(current) == len(held["rows"]) == unit["group"]["tracks"]
            assert set(current) == set(transferred) < set(both)
            assert set(current) == {
                (r["session_id"], t)
                for r in unit["group"]["receiver_partition"]
                for t in r["track_ids"]
            }
            assert all(
                r["held_observations"]
                == transferred[k]["held_observations"]
                == both[k]["held_observations"]
                for k, r in current.items()
            )
            assert (
                sum(r["held_observations"] for r in current.values())
                == unit["group"]["held_observations"]
            )
            prior_score = sum(r["held_log_score"] for r in transferred.values())
            both_score = sum(both[k]["held_log_score"] for k in current)
            assert abs(prior_score - before["held_log_score"]) < 1e-7
            deficit = prior_score - both_score
            assert deficit < 0
            delta = held["held_log_score"] - prior_score
            row.update(
                validated=True,
                tracks=len(current),
                held_observations=unit["group"]["held_observations"],
                training_gain=held["training_log_score"] - before["training_log_score"],
                prior_held_change_vs_both=deficit,
                held_gain_from_timing_refit=delta,
                refit_held_change_vs_both=held["held_log_score"] - both_score,
                fraction_prior_loss_recovered=delta / (-deficit),
                max_timing_gradient_check_difference=max(
                    c["absolute_difference"] for c in held["timing_gradient_checks"]
                ),
                timing_changes=(
                    np.asarray(chosen["timings"]) - unit["starts"][0]["timings"]
                ).tolist(),
            )
    rows.append(row)
for path in sorted(HERE.glob("runs/**/resources.txt")):
    text = path.read_text()
    seconds = 0.0
    for v in re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1).split(":"):
        seconds = seconds * 60 + float(v)
    resources.append(
        {
            "job": str(path.parent.relative_to(HERE)),
            "wall_s": seconds,
            "exit_code": int((path.parent / "exit-code.txt").read_text()),
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
            ),
        }
    )
valid = [r for r in rows if r["validated"]]
summary = {
    "units": rows,
    "execution_bindings_verified": len(bindings),
    "planned": len(rows),
    "validated": len(valid),
    "improved_vs_frozen_transfer": sum(r["held_gain_from_timing_refit"] > 0 for r in valid),
    "improved_vs_both_receiver_fit": sum(r["refit_held_change_vs_both"] > 0 for r in valid),
    "median_fraction_prior_loss_recovered": float(
        np.median([r["fraction_prior_loss_recovered"] for r in valid])
    )
    if valid
    else None,
}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
(HERE / "resource-summary.json").write_text(
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
    sub = [r for r in valid if r["source_receiver"] == rx]
    axes[0].scatter(
        [r["prior_held_change_vs_both"] for r in sub],
        [r["refit_held_change_vs_both"] for r in sub],
        color=color,
        label=f"RX{rx} source",
    )
    for size, marker in ((4, "o"), (8, "s")):
        subset = [r for r in sub if r["size"] == size]
        axes[1].scatter(
            [r["prior_held_change_vs_both"] for r in subset],
            [100 * r["fraction_prior_loss_recovered"] for r in subset],
            color=color,
            marker=marker,
            alpha=0.8,
            label=f"RX{rx}, {size} scans",
        )
axes[0].axhline(0, color="black", linestyle="--")
axes[0].axvline(0, color="black", linestyle="--")
axes[0].set(
    xlabel="Before timing refit: held change vs both (nats)",
    ylabel="After timing refit: held change vs both (nats)",
)
axes[1].axhline(100, color="black", linestyle="--")
axes[1].set(
    xlabel="Original cross-receiver held change (nats)", ylabel="Original loss recovered (%)"
)
axes[0].legend()
axes[1].legend()
fig.suptitle("Target timing refit · frozen source positions · matched held observations")
fig.savefig(HERE / "timing-recovery.png", dpi=170)
fig.savefig(HERE / "timing-recovery.svg")
print(json.dumps({k: v for k, v in summary.items() if k != "units"}, indent=2))
