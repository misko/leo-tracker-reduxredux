"""Verify diagnostic receipts and summarize training-gradient concentration."""

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
for path in [HERE / "input-seal.json", *HERE.glob("runs/*/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
rows, resources = [], []
for unit in plan["units"]:
    folder = HERE / "runs" / unit["unit_id"]
    code = int((folder / "exit-code.txt").read_text())
    resource = (folder / "resources.txt").read_text()
    seconds = 0.0
    for value in re.search(r"Elapsed \(wall clock\) time.*: (\S+)", resource).group(1).split(":"):
        seconds = seconds * 60 + float(value)
    resources.append(
        {
            "unit": unit["unit_id"],
            "exit_code": code,
            "wall_s": seconds,
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", resource).group(1)
            ),
        }
    )
    if code:
        rows.append({"unit_id": unit["unit_id"], "exit_code": code})
        continue
    r = json.loads((folder / "result.json").read_text())
    assert r["unit_id"] == unit["unit_id"]
    assert [a["session_id"] for a in r["records"]] == unit["session_ids"]
    assert len(r["records"]) == 8 and len(r["checks"]) == 16
    assert max(a["absolute_difference"] for a in r["checks"]) < 0.002
    norms = np.asarray([a["position_gradient_norm"] for a in r["tracks"]])
    assert abs(r["top_ten_norm_share"] - np.sort(norms)[-10:].sum() / norms.sum()) < 1e-12
    assert abs(r["effective_track_count"] - norms.sum() ** 2 / (norms @ norms)) < 1e-10
    frozen = json.loads((ROOT / unit["held_audit_path"]).read_text())
    assert len(r["tracks"]) == len(frozen["rows"])
    assert abs(sum(t["score"] for t in r["tracks"]) - unit["frozen_training_score"]) < 1e-7
    gradient = np.zeros(10)
    for record in r["records"]:
        subset = [t for t in r["tracks"] if t["session_id"] == record["session_id"]]
        local = np.sum([t["gradient"] for t in subset], axis=0)
        assert np.max(np.abs(local - record["gradient"])) < 1e-8
        gradient[:2] += local[:2]
        gradient[record["record_index"] + 2] = local[2]
    assert np.max(np.abs(gradient - frozen["full_training_gradient"])) < 1e-7
    top = sorted(r["tracks"], key=lambda t: t["position_gradient_norm"], reverse=True)[:10]
    receivers = []
    for receiver in sorted({str(t["receiver_id"]) for t in r["tracks"]}):
        subset = [t for t in r["tracks"] if str(t["receiver_id"]) == receiver]
        vector = np.sum([t["gradient"][:2] for t in subset], axis=0)
        receivers.append(
            {
                "software_receiver_id": receiver,
                "tracks": len(subset),
                "position_gradient": vector.tolist(),
                "norm_mass_share": float(
                    sum(t["position_gradient_norm"] for t in subset) / norms.sum()
                ),
            }
        )
    assert (
        np.max(np.abs(np.sum([g["position_gradient"] for g in receivers], axis=0) - gradient[:2]))
        < 1e-7
    )
    rows.append(
        {k: v for k, v in r.items() if k not in ("tracks", "checks")}
        | {
            "exit_code": 0,
            "track_count": len(r["tracks"]),
            "top_ten_tracks": top,
            "receiver_contributions": receivers,
            "max_gradient_check_difference": max(a["absolute_difference"] for a in r["checks"]),
            "gradient_norm_weighted_max_candidate_weight": float(
                sum(
                    t["position_gradient_norm"] * t["maximum_candidate_weight"] for t in r["tracks"]
                )
                / norms.sum()
            ),
        }
    )
summary = {"units": rows, "execution_bindings_verified": len(bindings)}
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
labels = [f"{ds}\n{block}" for ds in ("DS7", "DS8", "DS9") for block in ("early", "middle", "late")]
fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout="constrained")
for decay, color, shift in ((0, "tab:blue", -0.18), (10, "tab:orange", 0.18)):
    selected = [r for r in rows if r.get("decay_s") == decay]
    assert len(selected) == 9, (
        "Plot requires all diagnostics to succeed; failures retained in summary"
    )
    x = np.arange(9) + shift
    axes[0].bar(
        x,
        [100 * r["top_ten_norm_share"] for r in selected],
        width=0.36,
        color=color,
        label=f"Decay {decay} s",
    )
    axes[1].bar(x, [r["effective_track_count"] for r in selected], width=0.36, color=color)
axes[0].set_ylabel("Largest ten tracks' share\nof gradient norms (%)")
axes[1].set_ylabel("Effective track count\nfrom gradient norms")
axes[1].set_xticks(range(9), labels)
axes[0].legend()
fig.suptitle("Training-gradient concentration at frozen eight-scan fits")
fig.savefig(HERE / "concentration.png", dpi=170)
fig.savefig(HERE / "concentration.svg")
print(
    json.dumps(
        {"bindings": len(bindings), "successful_units": sum(r["exit_code"] == 0 for r in rows)},
        indent=2,
    )
)
