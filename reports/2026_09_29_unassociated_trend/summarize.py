"""Independently check frozen selections and report all contrast panels."""
# ruff: noqa: E501 -- Markdown prose and table rows remain readable as single strings.

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import BASE, CONTRAST, HERE, ROOT, digest, read, save, verify

plan = read(HERE / "plan.json")
original = read(BASE / "plan.json")
assert len(plan["groups"]) == len(plan["units"]) == 36
for arm, probability in (("q000", 0.0), ("q020", 0.2)):
    groups = [g for g in plan["groups"] if g["arm"] == arm]
    units = [u for u in plan["units"] if u["arm"] == arm]
    assert len(groups) == len(units) == 18
    for group, unit, old_group, old_unit in zip(
        groups, units, original["models"][0]["groups"], original["models"][0]["units"], strict=True
    ):
        assert {
            k: v for k, v in group.items() if k not in ("dataset_id", "base_unit_id", "arm")
        } == {k: v for k, v in old_group.items() if k != "dataset_id"}
        assert unit["unit_id"] == old_unit["unit_id"] + "_" + arm
        assert unit["background_probability"] == probability
        assert unit["starts"] == old_unit["starts"]
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
    baseline = read(CONTRAST / "runs" / unit["base_unit_id"] / "selection.json")["selected"]
    baseline_held = read(CONTRAST / "runs" / unit["base_unit_id"] / "held/result.json")
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
        if unit["background_probability"] == 0:
            assert held["normalization_replay"] is not None
            valid &= all(v < 1e-7 for v in held["normalization_replay"].values())
        else:
            assert held["normalization_replay"] is None
        assert bool(valid) == held["audit_passed"]
        assert (
            abs(sum(r["training_log_score"] for r in held["rows"]) - held["training_log_score"])
            < 1e-7
        )
        assert sum(r["held_observations"] for r in held["rows"]) == group["held_observations"]
        assert len(held["rows"]) == group["tracks"]
        assert abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"]) < 1e-7
        assert all(abs(sum(r["weights_given_signal"]) - 1) < 1e-10 for r in held["rows"])
        assert [(r["session_id"], r["track_id"], r["held_observations"]) for r in held["rows"]] == [
            (r["session_id"], r["track_id"], r["held_observations"]) for r in baseline_held["rows"]
        ]
        rho = np.array([r["signal_responsibility"] for r in held["rows"]])
        assert np.all((rho >= 0) & (rho <= 1))
        assert float(rho.sum()) == held["signal_responsibility_sum"]
        assert int((rho > 0.5).sum()) == held["tracks_signal_above_half"]
        np.testing.assert_array_equal(
            np.quantile(rho, [0, 0.25, 0.5, 0.75, 1]), held["signal_responsibility_quantiles"]
        )
        predictions[key] = held["rows"]
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
            "normalization_replay": held["normalization_replay"] if held else None,
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


paired = []
for control in [r for r in rows if r["arm"] == "q000"]:
    mixture = next(r for r in rows if r["base_unit"] == control["base_unit"] and r["arm"] == "q020")
    valid = control["audit_passed"] and mixture["audit_passed"]
    paired.append(
        {
            "unit": control["base_unit"],
            "dataset": control["dataset"],
            "block": control["block"],
            "size": control["size"],
            "audited": valid,
            "control_error_m": control["error_m"],
            "mixture_error_m": mixture["error_m"],
            "error_change_m": mixture["error_m"] - control["error_m"] if valid else None,
            "held_change_nats": mixture["held_total"] - control["held_total"] if valid else None,
        }
    )

matched = []
for arm in ("q000", "q020"):
    for ds in ("DS7", "DS8", "DS9"):
        for block in ("early", "middle", "late"):
            four, eight = f"{ds}_{block}_4_{arm}", f"{ds}_{block}_8_{arm}"
            valid = all(
                next(r for r in rows if r["unit"] == k)["audit_passed"] for k in (four, eight)
            )
            delta = None
            if valid:
                a = {(r["session_id"], r["track_id"]): r for r in predictions[four]}
                b = {(r["session_id"], r["track_id"]): r for r in predictions[eight]}
                assert a.keys() <= b.keys()
                assert all(a[k]["held_observations"] == b[k]["held_observations"] for k in a)
                delta = sum(b[k]["held_log_score"] - a[k]["held_log_score"] for k in a)
            matched.append(
                {
                    "arm": arm,
                    "dataset": ds,
                    "block": block,
                    "audited": valid,
                    "first_four_held_change_nats": delta,
                }
            )

valid = [r for r in paired if r["audited"]]
summary = {
    "rows": rows,
    "paired": paired,
    "matched": matched,
    "reference": reference,
    "paired_audits": len(valid),
    "position_improved": sum(r["error_change_m"] < 0 for r in valid),
    "held_improved": sum(r["held_change_nats"] > 0 for r in valid),
    "resources": receipts,
    "per_arm": {
        arm: {
            "audited": sum(r["audit_passed"] for r in rows if r["arm"] == arm),
            "nominal_sub_km": sum(
                r["audit_passed"] and r["error_m"] < 1000 for r in rows if r["arm"] == arm
            ),
        }
        for arm in ("q000", "q020")
    },
}
save(HERE / "summary.json", summary)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    controls = [r for r in rows if r["dataset"] == ds and r["arm"] == "q000"]
    ax.plot(
        range(6), [r["baseline_error_m"] / 1000 for r in controls], "o:", label="Prior contrast"
    )
    for arm, label, style in (
        ("q000", "Conditional bank", "s--"),
        ("q020", "20% trend prior", "o-"),
    ):
        subset = [r for r in rows if r["dataset"] == ds and r["arm"] == arm]
        ax.plot(
            range(6),
            [r["error_m"] / 1000 if r["audit_passed"] else np.nan for r in subset],
            style,
            label=label,
        )
    ax.axhline(1, color="gray", linewidth=1, linestyle=":")
    ax.set_xticks(range(6), [r["block"][:1].upper() + str(r["size"]) for r in controls])
    ax.set_title(ds)
    ax.set_xlabel("Early / middle / late; scans per set")
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Error to unsurveyed reference (km)")
axes[0].legend()
fig.suptitle("Explicit unassociated-trend alternative on fixed scan sets")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"comparison.{suffix}", dpi=160)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 5))
for ds, marker in zip(("DS7", "DS8", "DS9"), ("o", "s", "^"), strict=True):
    subset = [r for r in valid if r["dataset"] == ds]
    ax.scatter(
        [r["error_change_m"] for r in subset],
        [r["held_change_nats"] for r in subset],
        label=ds,
        marker=marker,
    )
    for r in subset:
        if abs(r["error_change_m"]) >= 100:
            ax.annotate(
                r["unit"].replace("_", " "),
                (r["error_change_m"], r["held_change_nats"]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
            )
ax.axhline(0, color="gray", linewidth=1)
ax.axvline(0, color="gray", linewidth=1)
ax.set_xlabel("Location error change (m): left is better")
ax.set_ylabel("Held log score change (nats): up is better")
ax.set_title("Trend mixture versus conditional-bank signal control")
ax.legend()
ax.grid(alpha=0.2)
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / f"tradeoffs.{suffix}", dpi=160)
plt.close(fig)

lines = [
    "# Conditional-bank signal and unassociated-trend comparison",
    "",
    "**Do not promote this trend mixture as a reliable sub-km localization solution.** Better held prediction did not translate into consistent geographic improvement; the nominal sub-km count is unchanged.",
    "",
    "The q000 control normalizes the satellite mixture over retained candidates passing the training horizon gate. q020 uses that same signal density plus a fixed 20% prior probability of an unassociated linear frequency trend, with a 2000 Hz/s slope scale. Both use normalized Student-t4 frequency-contrast densities. No receiver cone or separate RX timing is added.",
    "",
    f"Eight prelaunch tests pass. Both selected fits pass audit on {len(valid)}/18 paired panels. Among these, the trend branch improves location on {summary['position_improved']}/{len(valid)} and held prediction on {summary['held_improved']}/{len(valid)}. These are descriptive counts on dependent single-site panels.",
    "",
    f"Nominal sub-km sets passing numerical audit: q000 {summary['per_arm']['q000']['nominal_sub_km']}/18; q020 {summary['per_arm']['q020']['nominal_sub_km']}/18. These exposed-reference counts do not demonstrate calibrated resolution.",
    "",
    f"The late DS9 eight-scan error increases from {next(r['control_error_m'] for r in paired if r['unit']=='DS9_late_8')/1000:.3f} km to {next(r['mixture_error_m'] for r in paired if r['unit']=='DS9_late_8')/1000:.3f} km. Every DS7 and DS8 dataset/size median remains above 1 km. The broader goal remains open.",
    "",
    "## Median joint-set error",
    "",
    "Metres over early/middle/late sets; all three selected audits are required. Prior contrast is the preceding full-catalogue-divisor control; its training scores cannot be directly compared with these arms.",
    "",
    "| Dataset | Scans | Prior contrast | Conditional bank q000 | Trend mixture q020 |",
    "|---|---:|---:|---:|---:|",
]
for ds in ("DS7", "DS8", "DS9"):
    for size in (4, 8):
        controls = [
            r for r in rows if r["dataset"] == ds and r["size"] == size and r["arm"] == "q000"
        ]
        cells = [f"{np.median([r['baseline_error_m'] for r in controls]):,.1f}"]
        for arm in ("q000", "q020"):
            subset = [
                r for r in rows if r["dataset"] == ds and r["size"] == size and r["arm"] == arm
            ]
            cells.append(
                f"{np.median([r['error_m'] for r in subset]):,.1f}"
                if all(r["audit_passed"] for r in subset)
                else "Incomplete"
            )
        lines.append(f"| {ds} | {size} | " + " | ".join(cells) + " |")
lines += [
    "",
    "![Location comparison](comparison.png)",
    "",
    "![Location and held-score changes](tradeoffs.png)",
    "",
    "## Every planned fit",
    "",
    "Responsibilities are conditional-bank model weights, not measured satellite probabilities. Their sum is descriptive effective signal weight. Values near zero can leave geographic parameters uninformative even when numerical convergence succeeds. The complete results also retain qualifying-start position spread and training-score span; neither optimizer convergence nor a small exposed-reference error establishes identifiability.",
    "",
    "| Panel / arm | Error m | Audit | Qualified starts | Signal weight sum / tracks | Tracks signal > 0.5 |",
    "|---|---:|---|---:|---:|---:|",
]
for r in rows:
    error = f"{r['error_m']:.3f}" if r["error_m"] is not None else "No qualified fit"
    rho = (
        f"{r['signal_responsibility_sum']:.3f} / {r['tracks']}"
        if r["signal_responsibility_sum"] is not None
        else "Unavailable"
    )
    lines.append(
        f"| {r['unit']} | {error} | {'Pass' if r['audit_passed'] else 'FAIL — unvalidated'} | {r['qualified_starts']}/3 | {rho} | {r['tracks_signal_above_half']} |"
    )
lines += [
    "",
    "## Paired effect of the trend branch",
    "",
    "q020 minus q000; lower error and higher held score favor the trend branch. Invalid pairs remain in the planned denominator.",
    "",
    "| Panel | Error change m | Held change nats |",
    "|---|---:|---:|",
]
for r in paired:
    a = f"{r['error_change_m']:+.3f}" if r["audited"] else "Unvalidated"
    b = f"{r['held_change_nats']:+.3f}" if r["audited"] else "Unvalidated"
    lines.append(f"| {r['unit']} | {a} | {b} |")
lines += [
    "",
    "## Matched first-four held predictions",
    "",
    "Eight minus four, on the same first-four observations.",
    "",
    "| Arm | Dataset | Block | Held change nats |",
    "|---|---|---|---:|",
]
for r in matched:
    value = f"{r['first_four_held_change_nats']:+.3f}" if r["audited"] else "Unvalidated"
    lines.append(f"| {r['arm']} | {r['dataset']} | {r['block']} | {value} |")
lines += ["", "## Failures and evidence", ""]
for r in rows:
    if not r["audit_passed"]:
        lines.append(
            f"- {r['unit']}: selected audit failed or unavailable; see complete summary for stencils and checks."
        )
    for a in r["alternatives"]:
        if a["result"] is None or not a["result"]["qualified"]:
            reason = a["result"]["message"] if a["result"] else f"process exit {a['exit_code']}"
            lines.append(
                f"- {r['unit']} / {a['start']}: unqualified ({reason}). No completed run was retried."
            )
lines += [
    "",
    f"{sum(r['qualified_starts'] for r in rows)}/108 starts qualify; {sum(r['audit_passed'] for r in rows)}/36 selected audits pass. {len(receipts)} child receipts, {sum(r['exit_code'] == 0 for r in receipts)} exit zero. Total job wall time {sum(r['wall_seconds'] for r in receipts):.2f} s; maximum {max(r['wall_seconds'] for r in receipts):.2f} s; peak RSS {max(r['peak_rss_kib'] for r in receipts):,} KiB.",
    "",
    "All frozen hashes and selections were independently verified. Every selected fit checks all position/timing derivatives at two steps; q000 additionally checks the pointwise score correction, gradient and held prediction against the old contrast model. This is not global objective equivalence when visibility counts change. Distance calculations agree with independent vector geometry within 0.0001 m.",
    "",
    "The bank was data-selected and omits catalogue hypotheses. No calibrated association confidence, clutter classification, or complete detection likelihood is claimed. Fixed trend priors are uncalibrated prototype assumptions. Exposed, unsurveyed reference errors are not blind resolution evidence. No new RF data were collected.",
    "",
    "[Protocol](PROTOCOL.md), [tests](tests.log), [frozen plan](plan.json), [complete results and all starts](summary.json), [source/input seal](input-seal.json).",
    "",
    "[Next cone-model proposal](NEXT-CONE.md): transfer incompatible satellite prior mass to the explicit trend alternative, with shared scan geometry and separately tested predictive geometry. This is a design proposal, not an evaluated cone-plus-trend model.",
    "",
]
(HERE / "README.md").write_text("\n".join(lines))
for path in sorted(HERE.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.name != "evidence-sha256.json":
        bindings[str(path.relative_to(ROOT))] = digest(path)
save(HERE / "evidence-sha256.json", {"sha256": bindings})
print({k: v for k, v in summary.items() if k not in ("rows", "paired", "matched", "resources")})
