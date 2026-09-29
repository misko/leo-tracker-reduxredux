"""Independently check frozen selections and report all contrast panels."""
# ruff: noqa: E501 -- Markdown prose and table rows remain readable as single strings.

import json
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import BASE, HERE, ROOT, TREND, digest, read, save, verify

arm = sys.argv[1]
assert arm in ("c20", "c30", "c40", "c50")
width = int(arm[1:])
all_plan = read(HERE / "plan.json")
plan = {
    **all_plan,
    "groups": [g for g in all_plan["groups"] if g["arm"] == arm],
    "units": [u for u in all_plan["units"] if u["arm"] == arm],
}
original = read(BASE / "plan.json")
assert len(all_plan["groups"]) == len(all_plan["units"]) == 72
assert len(plan["groups"]) == len(plan["units"]) == 18
for group, unit, old_group, old_unit in zip(
    plan["groups"],
    plan["units"],
    original["models"][0]["groups"],
    original["models"][0]["units"],
    strict=True,
):
    assert {k: v for k, v in group.items() if k not in ("dataset_id", "base_unit_id", "arm")} == {
        k: v for k, v in old_group.items() if k != "dataset_id"
    }
    assert unit["unit_id"] == old_unit["unit_id"] + "_" + arm
    assert unit["background_probability"] == 0.2 and unit["half_angle_deg"] == width
    donor = read(TREND / "runs" / (unit["base_unit_id"] + "_q020") / "selection.json")["selected"]
    assert unit["starts"] == old_unit["starts"] + [{"source_dataset": "no_cone", "x": donor["x"]}]
    assert unit["session_ids"] == old_unit["session_ids"]
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
    baseline = read(TREND / "runs" / (unit["base_unit_id"] + "_q020") / "selection.json")[
        "selected"
    ]
    baseline_held = read(TREND / "runs" / (unit["base_unit_id"] + "_q020") / "held/result.json")
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
            axis, step = check["axis"], check["step"]
            crossing = bool(
                axis >= 2
                and np.floor((chosen["x"][axis] - step) * 4)
                != np.floor((chosen["x"][axis] + step) * 4)
            )
            assert crossing == check["crosses_grid_node"]
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
        assert held["no_cone_replay"] is not None
        valid &= all(v < 1e-7 for v in held["no_cone_replay"].values())
        assert bool(valid) == held["audit_passed"]
        assert (
            abs(sum(r["training_log_score"] for r in held["rows"]) - held["training_log_score"])
            < 1e-7
        )
        assert sum(r["held_observations"] for r in held["rows"]) == group["held_observations"]
        assert len(held["rows"]) == group["tracks"]
        assert abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"]) < 1e-7
        assert all(
            abs(sum(r["candidate_responsibilities"]) + r["background_responsibility"] - 1) < 1e-10
            for r in held["rows"]
        )
        assert [(r["session_id"], r["track_id"], r["held_observations"]) for r in held["rows"]] == [
            (r["session_id"], r["track_id"], r["held_observations"]) for r in baseline_held["rows"]
        ]
        rho = np.array([r["signal_responsibility"] for r in held["rows"]])
        assert np.all((rho >= -1e-10) & (rho <= 1 + 1e-10))
        assert float(rho.sum()) == held["signal_responsibility_sum"]
        assert int((rho > 0.5).sum()) == held["tracks_signal_above_half"]
        np.testing.assert_array_equal(
            np.quantile(rho, [0, 0.25, 0.5, 0.75, 1]), held["signal_responsibility_quantiles"]
        )
        for row, geo in zip(held["rows"], held["geometry_rows"], strict=True):
            assert (row["session_id"], row["track_id"]) == (geo["session_id"], geo["track_id"])
            assert (
                abs(sum(row["candidate_responsibilities"]) - row["signal_responsibility"]) < 1e-10
            )
            assert 0 <= geo["both_inside_signal_mass"] <= geo["training_inside_signal_mass"] + 1e-10
            assert geo["training_inside_signal_mass"] <= row["signal_responsibility"] + 1e-10
            assert 0 <= geo["held_inside_signal_mass"] <= row["signal_responsibility"] + 1e-10
            expected = (
                geo["both_inside_signal_mass"] / geo["training_inside_signal_mass"]
                if geo["training_inside_signal_mass"] > 0
                else None
            )
            assert expected == geo["conditional_held_inside_given_training_inside"]
        predictions[key] = held["rows"]
    generic = [r for r in eligible if r["start_id"] != "no_cone"]
    generic = max(generic, key=lambda r: r["training_log_score"]) if generic else None
    rows.append(
        {
            "unit": key,
            "base_unit": unit["base_unit_id"],
            "arm": unit["arm"],
            "tracks": group["tracks"],
            "signal_responsibility_sum": held["signal_responsibility_sum"] if held else None,
            "signal_responsibility_quantiles": held["signal_responsibility_quantiles"]
            if held
            else None,
            "tracks_signal_above_half": held["tracks_signal_above_half"] if held else None,
            "no_cone_replay": held["no_cone_replay"] if held else None,
            "held_total": held["held_log_score"] if held else None,
            "dataset": group["source_dataset"],
            "block": group["block"],
            "size": group["size"],
            "qualified_starts": len(eligible),
            "qualified_start_position_spread_m": max(
                (
                    1000 * float(np.linalg.norm(np.asarray(a["x"][:2]) - np.asarray(b["x"][:2])))
                    for a in eligible
                    for b in eligible
                ),
                default=None,
            ),
            "qualified_start_training_score_span": (
                max(r["training_log_score"] for r in eligible)
                - min(r["training_log_score"] for r in eligible)
                if eligible
                else None
            ),
            "audit_passed": bool(valid),
            "error_m": distance(chosen["estimate"]) if chosen else None,
            "baseline_error_m": distance(baseline["estimate"]),
            "held_change_nats": held["held_log_score"] - baseline_held["held_log_score"]
            if held
            else None,
            "selected": chosen,
            "generic_only_best": generic,
            "generic_only_error_m": distance(generic["estimate"]) if generic else None,
            "extra_start_training_gain": chosen["training_log_score"]
            - generic["training_log_score"]
            if chosen and generic
            else None,
            "conditional_controls_without_refit": held["conditional_controls_without_refit"]
            if held
            else None,
            "training_inside_signal_mass": sum(
                r["training_inside_signal_mass"] for r in held["geometry_rows"]
            )
            if held
            else None,
            "both_inside_signal_mass": sum(
                r["both_inside_signal_mass"] for r in held["geometry_rows"]
            )
            if held
            else None,
            "held_inside_signal_mass": sum(
                r["held_inside_signal_mass"] for r in held["geometry_rows"]
            )
            if held
            else None,
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


for path in sorted((HERE / "runs").glob("**/exit-code.txt")):
    if not path.relative_to(HERE).parts[1].endswith("_" + arm):
        continue
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

matched = []
for ds in ("DS7", "DS8", "DS9"):
    for block in ("early", "middle", "late"):
        four, eight = f"{ds}_{block}_4_{arm}", f"{ds}_{block}_8_{arm}"
        passed = all(next(r for r in rows if r["unit"] == k)["audit_passed"] for k in (four, eight))
        delta = None
        if passed:
            a = {(r["session_id"], r["track_id"]): r for r in predictions[four]}
            b = {(r["session_id"], r["track_id"]): r for r in predictions[eight]}
            assert a.keys() <= b.keys()
            assert all(a[k]["held_observations"] == b[k]["held_observations"] for k in a)
            delta = sum(b[k]["held_log_score"] - a[k]["held_log_score"] for k in a)
        matched.append(
            {"dataset": ds, "block": block, "audited": passed, "first_four_held_change_nats": delta}
        )
valid = [r for r in rows if r["audit_passed"]]
summary = {
    "arm": arm,
    "half_angle_deg": width,
    "rows": rows,
    "matched": matched,
    "reference": reference,
    "audited": len(valid),
    "planned": 18,
    "qualified_starts": sum(r["qualified_starts"] for r in rows),
    "position_improved": sum(r["error_m"] < r["baseline_error_m"] for r in valid),
    "held_improved": sum(r["held_change_nats"] > 0 for r in valid),
    "nominal_sub_km": sum(r["error_m"] < 1000 for r in valid),
    "nominal_beats_swapped_held": sum(
        r["held_total"] > r["conditional_controls_without_refit"]["swapped"]["held_log_score"]
        for r in valid
    ),
    "nominal_beats_copointed_held": sum(
        r["held_total"] > r["conditional_controls_without_refit"]["copointed"]["held_log_score"]
        for r in valid
    ),
    "resources": receipts,
}
save(HERE / f"summary-{arm}.json", summary)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["dataset"] == ds]
    ax.plot(
        range(6),
        [r["baseline_error_m"] / 1000 for r in subset],
        "o--",
        label="No-cone trend mixture",
    )
    ax.plot(
        range(6),
        [r["error_m"] / 1000 if r["audit_passed"] else np.nan for r in subset],
        "o-",
        label=f"{width}° half-angle",
    )
    ax.axhline(1, color="gray", linestyle=":", linewidth=1)
    ax.set_xticks(range(6), [r["block"][:1].upper() + str(r["size"]) for r in subset])
    ax.set_title(ds)
    ax.set_xlabel("Early / middle / late; scans per set")
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Error to unsurveyed reference (km)")
axes[0].legend()
fig.suptitle(f"Scan-consistent {width}° soft cones with normalized trend alternative")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"comparison-{arm}.{suffix}", dpi=160)
plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["dataset"] == ds]
    for field, label, style in (
        ("training_inside_signal_mass", "All training times", "o--"),
        ("both_inside_signal_mass", "Training + held times", "s-"),
    ):
        values = [
            100 * r[field] / r["signal_responsibility_sum"]
            if r["audit_passed"] and r["signal_responsibility_sum"] > 0
            else np.nan
            for r in subset
        ]
        ax.plot(range(6), values, style, label=label)
    ax.set_xticks(range(6), [r["block"][:1].upper() + str(r["size"]) for r in subset])
    ax.set_title(ds)
    ax.set_xlabel("Early / middle / late; scans per set")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Inside cone / total satellite weight (%)")
axes[0].legend()
fig.suptitle(f"Hard-cone support at {width}°; soft likelihood does not enforce hard support")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"support-{arm}.{suffix}", dpi=160)
plt.close(fig)

lines = [
    f"# {width}° cone/trend batch",
    "",
    f"**Completed arm: {len(valid)}/18 selected audits pass.** This arm alone does not complete the four-width experiment or establish calibrated sub-km accuracy.",
    "",
    f"{summary['qualified_starts']}/72 optimizer starts qualify. Among audited panels, position improves in {summary['position_improved']}/{len(valid)}, held prediction in {summary['held_improved']}/{len(valid)}, and {summary['nominal_sub_km']} nominal errors are below 1 km. Selection uses training score only. Counts across nested four/eight sets are dependent.",
    "",
    f"At the nominal fitted points, nominal axes beat swapped axes on held frequency in {summary['nominal_beats_swapped_held']}/{len(valid)} panels and co-pointed axes in {summary['nominal_beats_copointed_held']}/{len(valid)}. These controls are not refitted, so this does not validate orientation or travel direction. Their comparison must not be confused with the separate no-cone baseline comparison above.",
    "",
    "Each receiver keeps the same axis and width throughout the scan set. Cone compatibility uses the worst training angle with a 2° sigmoid edge and no floor; rejected satellite prior mass goes to the normalized unassociated trend. This is a soft compatibility model, not a hard cone or a calibrated beam. The held density keeps training weights fixed.",
    "",
    "## Median joint-set error",
    "",
    "Metres; all three block audits are required for each median.",
    "",
    "| Dataset | Scans | No-cone mixture | Cone/trend |",
    "|---|---:|---:|---:|",
]
for ds in ("DS7", "DS8", "DS9"):
    for size in (4, 8):
        subset = [r for r in rows if r["dataset"] == ds and r["size"] == size]
        value = (
            f"{np.median([r['error_m'] for r in subset]):,.1f}"
            if all(r["audit_passed"] for r in subset)
            else "Incomplete"
        )
        lines.append(
            f"| {ds} | {size} | {np.median([r['baseline_error_m'] for r in subset]):,.1f} | {value} |"
        )
lines += [
    "",
    f"![Location comparison](comparison-{arm}.png)",
    "",
    "## Every planned panel",
    "",
    "Held change is cone minus no-cone on identical observations. Unvalidated estimates remain visible, but are excluded from scientific aggregates.",
    "",
    "| Panel | No-cone m | Cone m | Held change nats | Audit |",
    "|---|---:|---:|---:|---|",
]
for r in rows:
    error = f"{r['error_m']:.3f}" if r["error_m"] is not None else "No qualified fit"
    held = f"{r['held_change_nats']:+.3f}" if r["held_change_nats"] is not None else "Unavailable"
    lines.append(
        f"| {r['base_unit']} | {r['baseline_error_m']:.3f} | {error} | {held} | {'Pass' if r['audit_passed'] else 'FAIL — unvalidated'} |"
    )
lines += [
    "",
    "## Geometry and conditional receiver controls",
    "",
    f"![Hard-cone support](support-{arm}.png)",
    "",
    "Signal weight is the sum of satellite responsibilities. Inside fractions divide training/all-observation hard-cone signal mass by that signal weight. They diagnose geometric compatibility of retained hypotheses, not verified satellite identities. Controls score swapped/co-pointed axes at the nominal fitted point without refitting; positive held differences favor nominal axes.",
    "",
    "| Panel | Signal weight / tracks | Training inside % | Train+held inside % | Nominal−swapped held | Nominal−co-pointed held |",
    "|---|---:|---:|---:|---:|---:|",
]
for r in rows:
    if r["signal_responsibility_sum"] is None:
        lines.append(f"| {r['base_unit']} | Unavailable | — | — | — | — |")
        continue
    rho = r["signal_responsibility_sum"]
    a = f"{100 * r['training_inside_signal_mass'] / rho:.2f}" if rho > 0 else "Undefined"
    b = f"{100 * r['both_inside_signal_mass'] / rho:.2f}" if rho > 0 else "Undefined"
    controls = r["conditional_controls_without_refit"]
    swap = r["held_total"] - controls["swapped"]["held_log_score"]
    co = r["held_total"] - controls["copointed"]["held_log_score"]
    lines.append(
        f"| {r['base_unit']} | {rho:.3f} / {r['tracks']} | {a} | {b} | {swap:+.3f} | {co:+.3f} |"
    )
lines += [
    "",
    "## Initialization and nested prediction",
    "",
    "The fourth start uses the old no-cone training-selected solution. Generic-only best results below expose any extra-start effect; they are not alternate selections after audit failures.",
    "",
    "| Panel | Generic-only m | Four-start m | Extra-start training gain |",
    "|---|---:|---:|---:|",
]
for r in rows:
    a = (
        f"{r['generic_only_error_m']:.3f}"
        if r["generic_only_error_m"] is not None
        else "Unavailable"
    )
    b = f"{r['error_m']:.3f}" if r["error_m"] is not None else "Unavailable"
    gain = (
        f"{r['extra_start_training_gain']:.6f}"
        if r["extra_start_training_gain"] is not None
        else "Unavailable"
    )
    lines.append(f"| {r['base_unit']} | {a} | {b} | {gain} |")
lines += [
    "",
    "Eight-minus-four held prediction on matched first-four observations:",
    "",
    "| Dataset | Block | Held change nats |",
    "|---|---|---:|",
]
for r in matched:
    v = f"{r['first_four_held_change_nats']:+.3f}" if r["audited"] else "Unvalidated"
    lines.append(f"| {r['dataset']} | {r['block']} | {v} |")
lines += ["", "## Failures and verification", ""]
for r in rows:
    if not r["audit_passed"]:
        lines.append(
            f"- {r['unit']}: selected audit failed or unavailable; detailed stencils are retained in the complete results."
        )
    for a in r["alternatives"]:
        if a["result"] is None or not a["result"]["qualified"]:
            reason = a["result"]["message"] if a["result"] else f"process exit {a['exit_code']}"
            lines.append(
                f"- {r['unit']} / {a['start']}: unqualified ({reason}). No completed run was retried."
            )
lines += [
    "",
    f"{len(receipts)} child processes, {sum(r['exit_code'] == 0 for r in receipts)} exit zero. Total child wall time {sum(r['wall_seconds'] for r in receipts):.2f} s; maximum {max(r['wall_seconds'] for r in receipts):.2f} s; peak RSS {max(r['peak_rss_kib'] for r in receipts):,} KiB.",
    "",
    "Complete frozen hashes and per-child evidence were verified; selections were reconstructed from every start. All selected fits check every coordinate at two finite-difference steps and replay the no-cone implementation against the old trend model. Independent distance formulas agree within 0.0001 m. Numerical convergence does not establish identifiability.",
    "",
    "Assumed world pose, provisional receiver mapping, retained-bank conditioning, uncalibrated priors and exposed unsurveyed reference remain limitations. No paired identity, reception/non-reception likelihood or travel-direction validation is claimed. No new RF data were collected.",
    "",
    f"[Full results](summary-{arm}.json), [protocol](PROTOCOL.md), [tests](tests.log), [frozen plan](plan.json).",
    "",
]
(HERE / f"RESULTS-{arm}.md").write_text("\n".join(lines))
completed = [a for a in ("c20", "c30", "c40", "c50") if (HERE / f"summary-{a}.json").exists()]
index = [
    "# Scan-consistent cones with an explicit trend alternative",
    "",
    f"**Checkpoint: {len(completed)}/4 frozen width arms completed.** The remaining arms are pending; no reliable sub-km or calibrated direction result is established by this checkpoint.",
    "",
    "This model conserves total prior mass when cone compatibility decreases: satellite mass transfers to the unassociated trend. Shared axes and widths apply throughout each scan set. The edge is soft, held geometry is audited separately, and cross-RX satellite identity remains unverified.",
    "",
    "The completed 20° arm is not an improvement to promote: held prediction worsens in 17/18 panels, nominal sub-km sets fall from three to two, and the late DS9 eight-scan error increases to 4.266 km. Nominal axes outperform swapped axes conditionally, but the soft model retains substantial outside-cone satellite weight. Wider arms remain separate frozen tests.",
    "",
    "| Half-angle | Status | Selected audits | Lower location error | Better held prediction |",
    "|---:|---|---:|---:|---:|",
]
for a in ("c20", "c30", "c40", "c50"):
    if a in completed:
        r = read(HERE / f"summary-{a}.json")
        index.append(
            f"| {a[1:]}° | [Complete](RESULTS-{a}.md) | {r['audited']}/18 | {r['position_improved']}/{r['audited']} | {r['held_improved']}/{r['audited']} |"
        )
    else:
        index.append(f"| {a[1:]}° | Pending | — | — | — |")
index += [
    "",
    "[Protocol](PROTOCOL.md), [frozen plan](plan.json), [nine prelaunch tests](tests.log), [source/input seal](input-seal.json).",
    "",
]
(HERE / "README.md").write_text("\n".join(index))
for path in sorted(HERE.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.name != "evidence-sha256.json":
        bindings[str(path.relative_to(ROOT))] = digest(path)
(HERE / "evidence-sha256.json").write_text(json.dumps({"sha256": bindings}, indent=2))
print({k: v for k, v in summary.items() if k not in ("rows", "matched", "resources")})
