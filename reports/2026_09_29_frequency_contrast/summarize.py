"""Independently check frozen selections and report all contrast panels."""
# ruff: noqa: E501 -- Markdown prose and table rows remain readable as single strings.

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import BASE, HERE, ROOT, digest, read, save, verify

plan = read(HERE / "plan.json")
original = read(BASE / "plan.json")
assert plan["groups"] == original["models"][0]["groups"]
assert plan["units"] == original["models"][0]["units"]
bindings = {}
for path in [HERE / "input-seal.json", *sorted((HERE / "runs").glob("**/seal.json"))]:
    for name, value in read(path)["sha256"].items():
        assert name not in bindings or bindings[name] == value
        bindings[name] = value
verify(bindings)
references = set()
for members in original["membership"].values():
    for member in members:
        path = ROOT / member["pose_path"]
        assert digest(path) == member["pose_sha256"]
        pose = read(path)["pose_authority"]
        references.add((pose["latitude_deg"], pose["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate):
    a, b = map(math.radians, reference)
    c, d = map(math.radians, (estimate["latitude_deg"], estimate["longitude_deg"]))
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    value = 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))
    u = np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])
    v = np.array([math.cos(c) * math.cos(d), math.cos(c) * math.sin(d), math.sin(c)])
    other = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))
    assert abs(value - other) < 1e-4
    return value


rows, predictions, receipts = [], {}, []
for unit, group in zip(plan["units"], plan["groups"], strict=True):
    key = unit["unit_id"]
    parent = HERE / "runs" / key
    selection = read(parent / "selection.json")
    eligible = []
    alternatives = []
    for start, stored in zip(unit["starts"], selection["runs"], strict=True):
        folder = parent / "fit" / start["source_dataset"]
        code = int((folder / "exit-code.txt").read_text())
        result = read(folder / "result.json") if code == 0 else None
        assert result == stored
        if result:
            assert result["initial"] == start["x"]
            assert result["session_ids"] == group["session_ids"]
            boundary = any(
                abs(v) > bound - 0.001
                for v, bound in zip(result["x"], [12, 12] + [5] * group["size"], strict=True)
            )
            qualified = (
                result["success"] and not boundary and max(map(abs, result["gradient"])) <= 0.01
            )
            assert qualified == result["qualified"]
            if qualified:
                eligible.append(result)
        alternatives.append(
            {
                "start": start["source_dataset"],
                "exit_code": code,
                "result": result,
                "error_m": distance(result["estimate"]) if result else None,
            }
        )
    chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert chosen == selection["selected"] and len(eligible) == selection["qualified_starts"]
    baseline = read(BASE / "t0" / key / "source-selection.json")["selected"]
    baseline_held = read(BASE / "t0" / key / "source_held/result.json")
    held_path = parent / "held/result.json"
    held = read(held_path) if held_path.exists() else None
    valid = False
    if held:
        assert int((parent / "held/exit-code.txt").read_text()) == 0
        assert held["session_ids"] == group["session_ids"]
        checks = held["gradient_checks"]
        assert len(checks) == 2 * (2 + group["size"])
        assert [c["axis"] for c in checks] == [
            a for a in range(2 + group["size"]) for _ in range(2)
        ]
        for check in checks:
            assert check["absolute_difference"] == abs(check["numerical"] - check["implemented"])
            assert check["implemented"] == held["full_training_gradient"][check["axis"]]
        assert [c["step"] for c in checks] == [0.001, 0.0005] * 2 + [0.0000625, 0.00003125] * group[
            "size"
        ]
        valid = abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
        valid &= all(
            c["absolute_difference"] < 0.002 and not c["crosses_grid_node"] for c in checks
        )
        agreements = [
            abs(checks[2 * a]["numerical"] - checks[2 * a + 1]["numerical"])
            for a in range(2, 2 + group["size"])
        ]
        assert agreements == held["timing_step_agreement"]
        valid &= all(v < 0.002 for v in agreements)
        assert bool(valid) == held["audit_passed"]
        assert (
            abs(sum(r["training_log_score"] for r in held["rows"]) - held["training_log_score"])
            < 1e-7
        )
        assert sum(r["held_observations"] for r in held["rows"]) == group["held_observations"]
        assert len(held["rows"]) == group["tracks"]
        assert abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"]) < 1e-7
        assert all(abs(sum(r["weights"]) - 1) < 1e-10 for r in held["rows"])
        assert [(r["session_id"], r["track_id"], r["held_observations"]) for r in held["rows"]] == [
            (r["session_id"], r["track_id"], r["held_observations"]) for r in baseline_held["rows"]
        ]
        predictions[key] = held["rows"]
    rows.append(
        {
            "unit": key,
            "dataset": group["source_dataset"],
            "block": group["block"],
            "size": group["size"],
            "qualified_starts": len(eligible),
            "audit_passed": bool(valid),
            "error_m": distance(chosen["estimate"]) if chosen else None,
            "baseline_error_m": distance(baseline["estimate"]),
            "held_change_nats": held["held_log_score"] - baseline_held["held_log_score"]
            if held
            else None,
            "selected": chosen,
            "alternatives": alternatives,
            "failed_checks": [
                c
                for c in held["gradient_checks"]
                if c["absolute_difference"] >= 0.002 or c["crosses_grid_node"]
            ]
            if held
            else None,
        }
    )

matched = []
for ds in ("DS7", "DS8", "DS9"):
    for block in ("early", "middle", "late"):
        four, eight = f"{ds}_{block}_4", f"{ds}_{block}_8"
        valid = all(next(r for r in rows if r["unit"] == k)["audit_passed"] for k in (four, eight))
        delta = None
        if valid:
            a = {(r["session_id"], r["track_id"]): r for r in predictions[four]}
            b = {(r["session_id"], r["track_id"]): r for r in predictions[eight]}
            assert a.keys() <= b.keys()
            assert all(a[k]["held_observations"] == b[k]["held_observations"] for k in a)
            delta = sum(b[k]["held_log_score"] - a[k]["held_log_score"] for k in a)
        matched.append(
            {"dataset": ds, "block": block, "audited": valid, "first_four_held_change_nats": delta}
        )

for path in sorted((HERE / "runs").glob("**/exit-code.txt")):
    resource = (path.parent / "resources.txt").read_text()
    fields = {}
    for line in resource.splitlines():
        if ": " in line:
            k, v = line.strip().rsplit(": ", 1)
            fields[k] = v
    parts = fields["Elapsed (wall clock) time (h:mm:ss or m:ss)"].split(":")
    wall = sum(float(v) * 60**i for i, v in enumerate(reversed(parts)))
    receipts.append(
        {
            "path": str(path.parent.relative_to(ROOT)),
            "exit_code": int(path.read_text()),
            "wall_seconds": wall,
            "peak_rss_kib": int(fields["Maximum resident set size (kbytes)"]),
        }
    )

valid = [r for r in rows if r["audit_passed"]]
summary = {
    "rows": rows,
    "matched": matched,
    "reference": reference,
    "audited_panels": len(valid),
    "planned_panels": len(rows),
    "qualified_starts": sum(r["qualified_starts"] for r in rows),
    "position_improved": sum(r["error_m"] < r["baseline_error_m"] for r in valid),
    "held_improved": sum(r["held_change_nats"] > 0 for r in valid),
    "sub_km": sum(r["error_m"] < 1000 for r in valid),
    "resources": receipts,
}
save(HERE / "summary.json", summary)
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["dataset"] == ds]
    ax.plot(range(6), [r["baseline_error_m"] / 1000 for r in subset], "o--", label="Baseline")
    ax.plot(
        range(6),
        [r["error_m"] / 1000 if r["audit_passed"] else np.nan for r in subset],
        "o-",
        label="Frequency contrasts",
    )
    ax.axhline(1, color="gray", linewidth=1, linestyle=":")
    ax.set_xticks(range(6), [r["block"][:1].upper() + str(r["size"]) for r in subset])
    ax.set_title(ds)
    ax.set_xlabel("Early / middle / late; scans per set")
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Error to unsurveyed reference (km)")
axes[0].legend()
fig.suptitle("Frequency-offset treatment on fixed consecutive scan sets")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"comparison.{suffix}", dpi=160)
plt.close(fig)
fig, ax = plt.subplots(figsize=(8, 5))
for ds, marker in zip(("DS7", "DS8", "DS9"), ("o", "s", "^"), strict=True):
    subset = [r for r in valid if r["dataset"] == ds]
    ax.scatter(
        [r["error_m"] - r["baseline_error_m"] for r in subset],
        [r["held_change_nats"] for r in subset],
        label=ds,
        marker=marker,
    )
    for r in subset:
        if abs(r["error_m"] - r["baseline_error_m"]) < 100:
            continue
        ax.annotate(
            r["unit"].replace("_", " "),
            (r["error_m"] - r["baseline_error_m"], r["held_change_nats"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
ax.axhline(0, color="gray", linewidth=1)
ax.axvline(0, color="gray", linewidth=1)
ax.set_xlabel("Position error change (m): left is better")
ax.set_ylabel("Held log score change (nats): up is better")
ax.set_title("Location and prediction gains can disagree\nOne point per audited scan set")
ax.legend()
ax.grid(alpha=0.2)
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"tradeoffs.{suffix}", dpi=160)
plt.close(fig)

lines = [
    "# Frequency-contrast location control",
    "",
    f"**{len(valid)}/18 selected panels pass the numerical audit; {summary['sub_km']} audited sets are below 1 km.** This is not evidence of reliable sub-km resolution across DS7/DS8/DS9.",
    "",
    "The model removes each track's constant frequency offset using a normalized Student-t4 density on frequency differences. It changes the likelihood dimension and predictive treatment of the offset, and removes the weak absolute-offset penalty. No cone, separate RX timing, or background branch is added.",
    "",
    f"Eight independent synthetic tests passed before freezing. {summary['qualified_starts']}/54 starts qualify. Among audited panels, position error improves in {summary['position_improved']}/{len(valid)} and held prediction improves in {summary['held_improved']}/{len(valid)}. These dependent, single-site comparisons are descriptive; reference coordinates are unsurveyed and previously exposed.",
    "",
    "## Median joint-set error",
    "",
    "Metres across early/middle/late. Incomplete means at least one planned block failed qualification or audit; do not silently omit it.",
    "",
    "| Dataset | Scans | Baseline | Frequency contrasts |",
    "|---|---:|---:|---:|",
]
for ds in ("DS7", "DS8", "DS9"):
    for size in (4, 8):
        subset = [r for r in rows if r["dataset"] == ds and r["size"] == size]
        median = (
            f"{np.median([r['error_m'] for r in subset]):,.1f}"
            if all(r["audit_passed"] for r in subset)
            else "Incomplete"
        )
        lines.append(
            f"| {ds} | {size} | {np.median([r['baseline_error_m'] for r in subset]):,.1f} | {median} |"
        )
lines += [
    "",
    "![Baseline versus contrasts](comparison.png)",
    "",
    "![Location versus held-prediction changes](tradeoffs.png)",
    "",
    "## Every planned panel",
    "",
    "Held change is contrast minus baseline, in nats over the identical held observations. Positive favors contrasts. Training scores are not compared across these different-dimensional models.",
    "",
    "| Panel | Baseline m | Contrast m | Held change nats | Audit |",
    "|---|---:|---:|---:|---|",
]
for r in rows:
    error = f"{r['error_m']:.3f}" if r["error_m"] is not None else "No qualified fit"
    held = f"{r['held_change_nats']:+.3f}" if r["held_change_nats"] is not None else "Unavailable"
    lines.append(
        f"| {r['unit']} | {r['baseline_error_m']:.3f} | {error} | {held} | {'Pass' if r['audit_passed'] else 'FAIL — unvalidated'} |"
    )
lines += [
    "",
    "## Matched first-four held predictions",
    "",
    "Eight-scan minus four-scan fit, scoring only the common first four scans.",
    "",
    "| Dataset | Block | Held change nats |",
    "|---|---|---:|",
]
for r in matched:
    value = f"{r['first_four_held_change_nats']:+.3f}" if r["audited"] else "Unvalidated"
    lines.append(f"| {r['dataset']} | {r['block']} | {value} |")
lines += [
    "",
    "## Audit and reproduction",
    "",
    f"{len(receipts)} child processes, {sum(r['exit_code'] == 0 for r in receipts)} exit zero; total job wall time {sum(r['wall_seconds'] for r in receipts):.2f} s, maximum {max(r['wall_seconds'] for r in receipts):.2f} s, peak RSS {max(r['peak_rss_kib'] for r in receipts):,} KiB. Process success is separate from scientific qualification.",
    "",
    "All source/input and child evidence hashes were verified; selections were reconstructed from each start. Every selected fit checks both step sizes on all position/timing coordinates, with explicit timing-node crossing checks. Both geographic distance formulas agree within 0.0001 m. The summary retains all starts and failed checks.",
    "",
    "The original retained candidate bank and horizon gate remain. Candidate weights do not establish satellite identities; no normalized full-catalogue detection/clutter model is claimed. A future unassociated-track branch must resolve omitted catalogue mass explicitly. No new RF data were collected.",
    "",
    "[Protocol](PROTOCOL.md), [tests](tests.log), [frozen plan](plan.json), [complete results](summary.json), [source/input seal](input-seal.json).",
    "",
    "## Next modeling step",
    "",
    "The [explicit unassociated-trend proposal](FOLLOWUP.md) describes how to reduce the geographic force of tracks poorly explained by satellite candidates. It requires a compatible normalized contrast density and an explicit retained-bank interpretation before mixture probabilities can be meaningful. This report does not implement that branch or establish receiver-cone consistency.",
    "",
]
failures = [
    f"- {r['unit']} / {a['start']}: "
    + (a["result"]["message"] if a["result"] else f"process exit {a['exit_code']}")
    for r in rows
    for a in r["alternatives"]
    if a["result"] is None or not a["result"]["qualified"]
]
if failures:
    lines += [
        "## Unqualified starts",
        "",
        *failures,
        "",
        "These starts remain excluded under the frozen success requirement, even if their final gradient is small. No completed start was rerun.",
        "",
    ]
(HERE / "README.md").write_text("\n".join(lines))
for path in sorted(HERE.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.name != "evidence-sha256.json":
        bindings[str(path.relative_to(ROOT))] = digest(path)
save(HERE / "evidence-sha256.json", {"sha256": bindings})
print({k: v for k, v in summary.items() if k not in ("rows", "matched", "resources")})
