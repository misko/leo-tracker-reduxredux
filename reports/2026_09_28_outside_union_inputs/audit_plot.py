"""Reconcile the complete frozen input ledger and assemble ready panels."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
outcomes = [r for group in json.loads((HERE / "outcomes.json").read_text()) for r in group]
assert {r["unit_id"] for r in outcomes} == {r["unit_id"] for r in plan["captures"]}
bindings = {}
for seal in [HERE / "input-seal.json", *HERE.glob("receipts/*/*/seal.json")]:
    for name, sha in json.loads(seal.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha, name
        bindings[name] = sha
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
rows, groups = [], []
for ds in ("DS7", "DS8", "DS9"):
    captures = [r for r in plan["captures"] if r["dataset_id"] == ds]
    valid, inputs = [], []
    for row in captures:
        outcome = next(r for r in outcomes if r["unit_id"] == row["unit_id"])
        for stage in outcome["stages"]:
            assert (
                int(
                    (
                        HERE / "receipts" / row["unit_id"] / stage["stage"] / "exit-code.txt"
                    ).read_text()
                )
                == stage["exit_code"]
            )
        entry = {
            "unit_id": row["unit_id"],
            "dataset_id": ds,
            "session_id": row["session_id"],
            "ordinal": row["ordinal"],
            "sample_rate_hz": row["sample_rate_hz"],
            "capture_start_utc_ns": row["capture_start_utc_ns"],
            "reused": row["reused_input"] is not None,
            "state": outcome["state"],
            "stages": outcome["stages"],
        }
        if outcome["state"] == "complete":
            validation = json.loads((HERE / "validated" / (row["unit_id"] + ".json")).read_text())
            assert validation["session_id"] == row["session_id"]
            assert validation["sample_rate_hz"] == row["sample_rate_hz"]
            if ds == "DS9":
                assert validation["mint_glrt_metrics_match"] is True
            input_row = validation["request"]["inputs"][0]
            assert input_row["manifest_sha256"] == row["manifest_sha256"]
            for artifact in input_row["artifacts"]:
                path = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                )
            entry.update(
                {
                    k: validation[k]
                    for k in (
                        "tracks",
                        "training_observations",
                        "held_observations",
                        "mint_glrt_metrics_match",
                    )
                }
            )
            entry["excluded_tracks"] = len(validation["eligibility_exclusions"])
            valid.append(entry)
            inputs.append(input_row)
        rows.append(entry)
    summary = {
        "dataset_id": ds,
        "requested_records": 15,
        "validated_records": len(valid),
        "ready": len(valid) == 15,
        "sample_rates_hz": dict(sorted(Counter(c["sample_rate_hz"] for c in captures).items())),
        "start_span_hours": (
            captures[-1]["capture_start_utc_ns"] - captures[0]["capture_start_utc_ns"]
        )
        / 3.6e12,
        "tracks": sum(r["tracks"] for r in valid),
        "training_observations": sum(r["training_observations"] for r in valid),
        "held_observations": sum(r["held_observations"] for r in valid),
    }
    if summary["ready"]:
        summary["session_ids"] = [r["session_id"] for r in captures]
        summary["inputs"] = inputs
    groups.append(summary)
resources = []
for path in sorted(HERE.glob("receipts/*/*/resources.txt")):
    data = path.read_text()
    elapsed = re.search(r"Elapsed .*: (\d+):(\d+\.\d+)", data)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", data)
    resources.append(
        {
            "stage": str(path.parent.relative_to(HERE)),
            "wall_s": int(elapsed[1]) * 60 + float(elapsed[2]),
            "max_rss_kib": int(rss[1]),
            "exit_code": int((path.parent / "exit-code.txt").read_text()),
        }
    )
summary = {
    "groups": groups,
    "rows": rows,
    "verified_bindings": len(bindings),
    "resources": resources,
    "job_wall_sum_s": sum(r["wall_s"] for r in resources),
    "max_job_wall_s": max(r["wall_s"] for r in resources),
    "max_rss_kib": max(r["max_rss_kib"] for r in resources),
}
(HERE / "audit-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
with (HERE / "panel-inputs.json").open("x") as stream:
    json.dump(
        {
            "config": plan["config"],
            "all_panels_ready": all(g["ready"] for g in groups),
            "groups": groups,
        },
        stream,
        indent=2,
    )
fig, ax = plt.subplots(figsize=(11, 4), layout="constrained")
for y, ds in enumerate(("DS7", "DS8", "DS9")):
    captures = [r for r in rows if r["dataset_id"] == ds]
    start = captures[0]["capture_start_utc_ns"]
    for row in captures:
        x = (row["capture_start_utc_ns"] - start) / 3.6e12
        marker = "o" if row["state"] == "complete" else "x"
        ax.scatter(x, y, marker=marker, color=f"C{y}", s=65)
        ax.annotate(
            str(row["ordinal"]),
            (x, y),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
ax.set_yticks(range(3), ["DS7", "DS8", "DS9"])
ax.set_ylim(-0.5, 2.6)
ax.set_xlabel("Hours from the first selected capture start in each dataset")
ax.set_title(
    "Frozen fifteen-record temporal panels · labels are chronological ordinals\n"
    "Circle: validated input; cross: unresolved input"
)
ax.grid(axis="x", alpha=0.25)
fig.savefig(HERE / "temporal-coverage.png", dpi=170)
fig.savefig(HERE / "temporal-coverage.svg")
print(
    json.dumps(
        {
            "groups": [{k: v for k, v in g.items() if k != "inputs"} for g in groups],
            "resources": {
                k: summary[k]
                for k in ("verified_bindings", "job_wall_sum_s", "max_job_wall_s", "max_rss_kib")
            },
        },
        indent=2,
    )
)
