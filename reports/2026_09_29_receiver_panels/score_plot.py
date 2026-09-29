"""Audit consecutive-panel fits and compare nested four/eight observations."""

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_29_consecutive_panels"
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("t*/**/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
spec = plan["models"][0]
assert len(plan["models"]) == 1 and spec["decay_s"] == 0
assert len(spec["units"]) == len(spec["groups"]) == 36
sessions = [r["session_id"] for records in plan["membership"].values() for r in records]
assert len(sessions) == 216 and len(set(sessions)) == 72
assert Counter(Counter(sessions).values()) == {2: 36, 4: 36}
baseline_rows = {r["unit"]: r for r in json.loads((PREVIOUS / "scores.json").read_text())["rows"]}
references = set()
for records in plan["membership"].values():
    for record in records:
        pose = ROOT / record["pose_path"]
        assert hashlib.sha256(pose.read_bytes()).hexdigest() == record["pose_sha256"]
        authority = json.loads(pose.read_text())["pose_authority"]
        references.add((authority["latitude_deg"], authority["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate, reference=reference):
    lat, lon = estimate["latitude_deg"], estimate["longitude_deg"]
    value = horizontal_error_m(lat, lon, *reference)

    def vector(a, b):
        a, b = math.radians(a), math.radians(b)
        return np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])

    a, b = vector(lat, lon), vector(*reference)
    independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - independent) < 1e-4
    return value


rows, held_rows = [], {}
for unit, group in zip(spec["units"], spec["groups"], strict=True):
    key, ds, size = group["dataset_id"], group["source_dataset"], group["size"]
    manifest = json.loads((ROOT / group["manifest_path"]).read_text())
    captures = sorted(
        manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
    )
    begin = {"early": 0, "middle": (len(captures) - 8) // 2, "late": len(captures) - 8}[
        group["block"]
    ]
    assert size in (4, 8) and group["start_index"] == begin
    expected = [r["session_id"] for r in captures[begin : begin + size]]
    assert group["session_ids"] == unit["session_ids"] == expected
    assert [r["session_id"] for r in plan["membership"][key]] == expected
    assert [r["session_id"] for r in group["inputs"]] == expected
    assert unit["source_datasets"] == [key] and unit["excluded_dataset"] is None
    assert unit["starts"] == [
        {"source_dataset": label, "x": xy + [0] * size}
        for label, xy in (("origin", [0, 0]), ("southeast", [3, -3]), ("northwest", [-3, 3]))
    ]
    parent = HERE / "t0" / key
    selection = json.loads((parent / "source-selection.json").read_text())
    eligible, alternatives = [], []
    assert [r["start_id"] for r in selection["runs"]] == [
        s["source_dataset"] for s in unit["starts"]
    ]
    for run in selection["runs"]:
        folder = parent / "source_fit" / run["start_id"]
        assert int((folder / "exit-code.txt").read_text()) == run["exit_code"]
        fit = run["result"]
        if fit is None:
            assert run["exit_code"] != 0
            alternatives.append({"start": run["start_id"], "exit_code": run["exit_code"]})
            continue
        assert fit == json.loads((folder / "result.json").read_text())
        assert fit["session_ids"] == expected
        assert fit["initial"] == next(
            s["x"] for s in unit["starts"] if s["source_dataset"] == run["start_id"]
        )
        boundary = any(
            abs(v) > b - 0.001 for v, b in zip(fit["x"], [12, 12] + [5] * size, strict=True)
        )
        assert fit["qualified"] == bool(
            fit["success"] and not boundary and max(map(abs, fit["gradient"])) <= 0.01
        )
        if fit["qualified"]:
            eligible.append(fit)
        alternatives.append(
            {"start": run["start_id"], "error_m": distance(fit["estimate"]), "fit": fit}
        )
    chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selection["selected"] == chosen and selection["qualified_starts"] == len(eligible)
    row = {
        "unit": key,
        "dataset": ds,
        "block": group["block"],
        "size": size,
        "ordinals": [begin + 1, begin + size],
        "qualified_starts": len(eligible),
        "selected": chosen,
        "alternatives": alternatives,
        "receiver_id": group["receiver_id"],
        "panel_id": group["panel_id"],
        "both_receiver_error_m": baseline_rows[group["panel_id"]]["error_m"],
    }
    if chosen is not None:
        folder = parent / "source_held"
        assert int((folder / "exit-code.txt").read_text()) == 0
        held = json.loads((folder / "result.json").read_text())
        assert held["session_ids"] == expected
        assert abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
        for field in ("training_log_score", "held_log_score"):
            assert abs(sum(r[field] for r in held["rows"]) - held[field]) < 1e-7
        assert len(held["position_gradient_check"]) == 4
        assert max(g["absolute_difference"] for g in held["position_gradient_check"]) < 0.002
        current = {(r["session_id"], r["track_id"]): r for r in held["rows"]}
        assert chosen["receiver_id"] == held["receiver_id"] == group["receiver_id"]
        assert set(current) == {
            (r["session_id"], t) for r in group["receiver_partition"] for t in r["track_ids"]
        }
        assert len(current) == len(held["rows"]) == group["tracks"]
        assert {k[0] for k in current} == set(expected)
        train_count = held_count = 0
        for item in group["inputs"]:
            artifact = next(a for a in item["artifacts"] if a["kind"] == "observations")
            for track in json.loads(Path(artifact["path"]).read_text())["tracks"]:
                k = item["session_id"], track["track_id"]
                if k in current:
                    assert str(track["receiver_id"]) == group["receiver_id"]
                    n = sum(track["training_mask"])
                    nh = len(track["training_mask"]) - n
                    assert n >= 2 and nh >= 1 and nh == current[k]["held_observations"]
                    train_count += n
                    held_count += nh
        assert (
            train_count == group["training_observations"]
            and held_count == group["held_observations"]
        )
        held_rows[key] = current
        row.update(
            error_m=distance(chosen["estimate"]),
            tracks=len(current),
            training_observations=train_count,
            held_observations=held_count,
            gradient_check=held["position_gradient_check"],
            held_log_score=held["held_log_score"],
        )
        old = json.loads(
            (PREVIOUS / "t0" / group["panel_id"] / "source_held/result.json").read_text()
        )
        previous = {(r["session_id"], r["track_id"]): r for r in old["rows"]}
        other = held["other_receiver"]
        assert other["receiver_id"] == ("1" if group["receiver_id"] == "0" else "0")
        assert other["position_and_timings"] == chosen["x"]
        target = {(r["session_id"], r["track_id"]): r for r in other["rows"]}
        assert len(target) == len(other["rows"]) and not set(current) & set(target)
        assert set(current) | set(target) == set(previous)
        assert {k[0] for k in target} == set(expected)
        for field in ("training_log_score", "held_log_score"):
            assert abs(sum(r[field] for r in other["rows"]) - other[field]) < 1e-7
        comparisons = []
        for label, values in (("own", current), ("other", target)):
            assert all(
                v["held_observations"] == previous[k]["held_observations"]
                for k, v in values.items()
            )
            comparisons.append(
                {
                    "receiver": label,
                    "tracks": len(values),
                    "held_observations": sum(v["held_observations"] for v in values.values()),
                    "training_change_vs_both": sum(
                        v["training_log_score"] - previous[k]["training_log_score"]
                        for k, v in values.items()
                    ),
                    "held_change_vs_both": sum(
                        v["held_log_score"] - previous[k]["held_log_score"]
                        for k, v in values.items()
                    ),
                }
            )
        row["receiver_comparisons"] = comparisons
    rows.append(row)
pairs, aggregates = [], []
for ds in ("DS7", "DS8", "DS9"):
    for block in ("early", "middle", "late"):
        for receiver in ("0", "1"):
            assert (
                plan["membership"][f"{ds}_{block}_4_rx{receiver}"]
                == plan["membership"][f"{ds}_{block}_8_rx{receiver}"][:4]
            )
        for size in (4, 8):
            selected = [
                next(r for r in rows if r["unit"] == f"{ds}_{block}_{size}_rx{rx}")
                for rx in ("0", "1")
            ]
            pair = {
                "dataset": ds,
                "block": block,
                "size": size,
                "available": all(r["selected"] is not None for r in selected),
            }
            if pair["available"]:
                a, b = [r["selected"] for r in selected]
                pair["receiver_position_separation_m"] = distance(
                    a["estimate"], (b["estimate"]["latitude_deg"], b["estimate"]["longitude_deg"])
                )
                pair["timing_difference_rx1_minus_rx0_s"] = (
                    np.asarray(b["x"])[2:] - np.asarray(a["x"])[2:]
                ).tolist()
            pairs.append(pair)
    for size in (4, 8):
        for receiver in ("0", "1"):
            subset = [
                r
                for r in rows
                if r["dataset"] == ds and r["size"] == size and r["receiver_id"] == receiver
            ]
            assert len(subset) == 3
            errors = [r["error_m"] for r in subset if "error_m" in r]
            aggregates.append(
                {
                    "dataset": ds,
                    "size": size,
                    "receiver_id": receiver,
                    "attempted": 3,
                    "qualified": len(errors),
                    "subkm": sum(e < 1000 for e in errors),
                    "median_joint_panel_error_m": float(np.median(errors)) if errors else None,
                }
            )
scores = {
    "rows": rows,
    "receiver_pairs": pairs,
    "aggregates": aggregates,
    "reference": reference,
    "execution_bindings_verified": len(bindings),
}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
resources = []
for path in sorted(HERE.glob("t*/**/resources.txt")):
    text = path.read_text()
    seconds = 0.0
    for part in re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1).split(":"):
        seconds = seconds * 60 + float(part)
    resources.append(
        {
            "job": str(path.parent.relative_to(HERE)),
            "wall_s": seconds,
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
            ),
            "exit_code": int((path.parent / "exit-code.txt").read_text()),
        }
    )
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
fig, axes = plt.subplots(2, 3, figsize=(13, 8), sharey=True, layout="constrained")
for index, size in enumerate((4, 8)):
    for ax, ds in zip(axes[index], ("DS7", "DS8", "DS9"), strict=True):
        for receiver, color in (("0", "tab:orange"), ("1", "tab:blue")):
            subset = [
                r
                for r in rows
                if r["dataset"] == ds and r["size"] == size and r["receiver_id"] == receiver
            ]
            ax.plot(
                range(3),
                [r.get("error_m", np.nan) for r in subset],
                "o-",
                color=color,
                label=f"RX{receiver} fit",
            )
        ax.plot(
            range(3),
            [
                baseline_rows[f"{ds}_{block}_{size}"]["error_m"]
                for block in ("early", "middle", "late")
            ],
            "x--",
            color="tab:gray",
            label="Both receivers",
        )
        ax.axhline(1000, color="black", linestyle="--", alpha=0.6, label="1 km")
        ax.set_xticks(range(3), ["Early", "Middle", "Late"])
        ax.set_title(f"{ds} · {size} scans")
axes[0, 0].set_ylim(
    0,
    1.1
    * max(
        1000, *(r.get("error_m", 0) for r in rows), *(r["error_m"] for r in baseline_rows.values())
    ),
)
for ax in axes[:, 0]:
    ax.set_ylabel("Joint position error (m)")
handles, labels = axes[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc="outside lower center", ncol=4)
fig.suptitle("Receiver-separated consecutive panels · unsurveyed reference")
fig.savefig(HERE / "receivers.png", dpi=170)
fig.savefig(HERE / "receivers.svg")
print(json.dumps({"aggregates": aggregates, "bindings": len(bindings)}, indent=2))
