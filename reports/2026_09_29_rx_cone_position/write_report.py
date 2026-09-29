"""Assemble all predeclared widths, retain failures, and seal completed evidence."""

import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LABELS = ("c20", "c30", "c40", "c50")
summaries = {k: json.loads((HERE / f"summary-{k}.json").read_text()) for k in LABELS}
resources = {k: json.loads((HERE / f"resources-{k}.json").read_text()) for k in LABELS}
rows = [r for s in summaries.values() for r in s["rows"]]
assert len(rows) == 72 and len({r["unit"] for r in rows}) == 72
assert all(len(s["no_cone_validations"]) == 18 for s in summaries.values())
valid = [r for r in rows if r["validated"]]
starts = [(r["unit"], a) for r in rows for a in r["alternatives"]]
jobs = [j for s in resources.values() for j in s["jobs"]]
plan = json.loads((HERE / "plan.json").read_text())
units = {u["unit_id"]: u for u in plan["units"]}
association = {}
for label, summary in summaries.items():
    distances, changes, memberships = [], 0, []
    for row in summary["rows"]:
        if not row["validated"]:
            continue
        unit = units[row["unit"]]
        before = json.loads((ROOT / unit["baseline_audit"]).read_text())["rows"]
        after = json.loads((HERE / "runs" / row["unit"] / "held/result.json").read_text())["rows"]
        old = {(r["session_id"], r["track_id"]): r for r in before}
        new = {(r["session_id"], r["track_id"]): r for r in after}
        assert old.keys() == new.keys()
        panel_distances, panel_changes = [], 0
        for key in old:
            w0, w1 = np.asarray(old[key]["weights"]), np.asarray(new[key]["weights"])
            assert w0.shape == w1.shape
            assert abs(w0.sum() - 1) < 1e-8 and abs(w1.sum() - 1) < 1e-8
            assert np.all(w0 >= 0) and np.all(w1 >= 0)
            tv = float(0.5 * abs(w0 - w1).sum())
            assert -1e-12 <= tv <= 1 + 1e-8
            panel_distances.append(tv)
            panel_changes += int(np.argmax(w0) != np.argmax(w1))
        distances.extend(panel_distances)
        changes += panel_changes
        memberships.append(
            {
                "unit": row["unit"],
                "track_memberships": len(panel_distances),
                "most_probable_candidate_changes": panel_changes,
                "mean_total_variation": float(np.mean(panel_distances)),
            }
        )
    association[label] = {
        "panels": memberships,
        "track_memberships": len(distances),
        "most_probable_candidate_changes": changes,
        "mean_total_variation": float(np.mean(distances)) if distances else None,
        "median_total_variation": float(np.median(distances)) if distances else None,
        "p95_total_variation": float(np.quantile(distances, 0.95)) if distances else None,
    }
(HERE / "association-diagnostic.json").write_text(json.dumps(association, indent=2) + "\n")


def value(v):
    return "Incomplete" if v is None else f"{v:,.0f}"


fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
for ax, size in zip(axes, (4, 8), strict=True):
    for ds, color in zip(("DS7", "DS8", "DS9"), ("#0072B2", "#D55E00", "#009E73"), strict=True):
        series = [
            next(a for a in summaries[k]["aggregates"] if a["dataset"] == ds and a["size"] == size)
            for k in LABELS
        ]
        ax.plot(
            [20, 30, 40, 50],
            [
                a["median_error_m"] if a["median_error_m"] is not None else float("nan")
                for a in series
            ],
            "o-",
            color=color,
            label=ds,
        )
        baseline = sorted(
            r["baseline_error_m"]
            for r in summaries["c20"]["rows"]
            if r["dataset"] == ds and r["size"] == size
        )[1]
        ax.axhline(baseline, color=color, linestyle=":", alpha=0.65)
    ax.axhline(1000, color="black", linestyle="--", linewidth=1, label="1 km")
    ax.set(
        title=f"{size} consecutive scans",
        xlabel="Cone half-angle (degrees)",
        xticks=[20, 30, 40, 50],
    )
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Median joint-set position error (m)")
axes[1].legend()
fig.suptitle(
    "Fixed receiver cones · dotted lines: no-cone baseline\n"
    "Gaps indicate incomplete audits; three sets per dataset / size"
)
fig.tight_layout()
for ext in ("png", "svg"):
    fig.savefig(HERE / f"cone-width-comparison.{ext}", dpi=160)

lines = [
    "# Joint location with scan-consistent receiver cones",
    "",
    "**Do not promote this soft-cone model as a reliable sub-km solution.** "
    "No tested width establishes sub-km performance across DS7/DS8/DS9. Every "
    "complete DS7 and DS8 median remains above 1 km, and the late DS9 eight-scan "
    "error exceeds 3 km in every width arm. The broad goal remains open.",
    "",
    "The complete predeclared 20°, 30°, 40°, and 50° half-angle sweep fits one common "
    "position and one timing per recording, with fixed receiver axes and cone widths "
    "throughout each scan set. Each candidate keeps one trajectory across its track. "
    "The nominal axes point 10° west/east of zenith (20° apart); that world pose and "
    "receiver mapping remain assumptions, not calibrated measurements. Half-angle "
    "means a 20° arm has a 40° full opening; this interpretation is provisional.",
    "",
    f"**{len(valid)}/72 selected solutions pass the numerical audit.** "
    f"Among those, {sum(r['error_m'] < r['baseline_error_m'] for r in valid)} "
    f"improve reference position error and {sum(r['held_gain'] > 0 for r in valid)} "
    "improve held Doppler prediction. These are paired descriptive counts across "
    "dependent sensitivity arms, not independent trials or a width-selection rule.",
    "",
    "## Position results",
    "",
    "Median error in metres across early/middle/late scan sets. Each cell requires "
    "all three selected fits to pass. These are joint set estimates, not single-scan "
    "medians. Four-scan sets are nested in eight-scan sets.",
    "",
    "| Scans | Cone half-angle | DS7 | DS8 | DS9 |",
    "|---:|---|---:|---:|---:|",
]
for size in (4, 8):
    baseline = [
        sorted(
            r["baseline_error_m"]
            for r in summaries["c20"]["rows"]
            if r["dataset"] == ds and r["size"] == size
        )[1]
        for ds in ("DS7", "DS8", "DS9")
    ]
    lines.append(f"| {size} | No cone | " + " | ".join(map(value, baseline)) + " |")
    for k in LABELS:
        values = [
            next(
                a["median_error_m"]
                for a in summaries[k]["aggregates"]
                if a["dataset"] == ds and a["size"] == size
            )
            for ds in ("DS7", "DS8", "DS9")
        ]
        lines.append(f"| {size} | {k[1:]}° | " + " | ".join(map(value, values)) + " |")
lines += [
    "",
    "![Cone-width comparison](cone-width-comparison.png)",
    "",
    "| Half-angle | Audited / planned | Lower position error | "
    "Better held Doppler | Audited sub-km sets |",
    "|---:|---:|---:|---:|---:|",
]
for k, s in summaries.items():
    v = [r for r in s["rows"] if r["validated"]]
    lines.append(
        f"| {k[1:]}° | {len(v)}/18 | "
        f"{sum(r['error_m'] < r['baseline_error_m'] for r in v)}/{len(v)} | "
        f"{sum(r['held_gain'] > 0 for r in v)}/{len(v)} | "
        f"{sum(r['error_m'] < 1000 for r in v)} |"
    )
lines += [
    "",
    "The following diagnostics use only audited panels. A negative median error "
    "change favors the cone model. Controls are evaluated at the nominal fitted "
    "point and are not independently optimized alternatives. Neither a positive "
    "control count nor a small reference-error change establishes direction evidence.",
    "",
    "| Half-angle | Median error change (m) | Median held change (nats) | "
    "Nominal beats swapped | Nominal beats co-pointed |",
    "|---:|---:|---:|---:|---:|",
]
for k, s in summaries.items():
    v = [r for r in s["rows"] if r["validated"]]
    if v:
        delta = statistics.median(r["error_m"] - r["baseline_error_m"] for r in v)
        held_delta = statistics.median(r["held_gain"] for r in v)
        counts = [
            sum(r["conditional_controls"][control]["nominal_minus_control_held"] > 0 for r in v)
            for control in ("swapped", "copointed")
        ]
        lines.append(
            f"| {k[1:]}° | {delta:+.3f} | {held_delta:+.3f} | "
            f"{counts[0]}/{len(v)} | {counts[1]}/{len(v)} |"
        )
    else:
        lines.append(f"| {k[1:]}° | Unavailable | Unavailable | 0/0 | 0/0 |")
lines += [
    "",
    "## What consistency means here",
    "",
    "For a candidate, the cone factor uses its maximum boresight angle over all "
    "training observations in that track. The factor is 0.01 + 0.99 times a sigmoid "
    "with a fixed 2° edge. It reweights the Doppler candidate mixture while location "
    "and timing are fitted. Its 1% floor retains out-of-cone explanations; this is "
    "a soft compatibility factor, not a calibrated beam or clutter probability. "
    "The earlier [support audit](../2026_09_29_rx_cone_consistency/README.md) tested "
    "all sixteen RX0/RX1 width pairs; this location study tests four equal-width pairs.",
    "",
    "A limitation follows directly from the mixture: if every candidate of a track "
    "has the same locally constant cone factor c, its mixture becomes c times the "
    "no-cone mixture. That adds log(c) to training score but leaves its position "
    "gradient and normalized candidate weights unchanged; the factor also cancels "
    "from the conditional held score. The soft floor approaches this regime far "
    "outside a narrow cone. Thus the floor retains unexplained tracks but does not "
    "automatically reduce their frequency-based pull on position. This algebraic "
    "limitation is not a measured count of floor-saturated tracks.",
    "",
    "Held Doppler predictions condition on the same training-derived factor. Held "
    "angles do not change that factor. Consequently this does not enforce a hard "
    "cone at every held sample, score non-detections, or verify shared satellite "
    "identity across receiver tracks. Those require a detection model and independently "
    "supported cross-RX associations. Swapped-axis and co-pointed controls are evaluated "
    "at the nominal fitted point without refitting, so they are conditional diagnostics.",
    "",
    "## Candidate-weight changes",
    "",
    "This post-fit descriptive diagnostic compares training candidate weights with "
    "the no-cone baseline on audited panels. Total variation is half the sum of "
    "absolute weight differences: zero means identical distributions, one means "
    "disjoint support. Changes combine the cone factor and refitted position/timing; "
    "they do not isolate the cone's direct contribution. Most-probable candidates "
    "are retained-bank hypotheses, not verified identities. Track appearances repeat "
    "across nested four/eight sets and must not be counted as independent trials.",
    "",
    "| Half-angle | Audited track appearances | Most-probable candidate changes | "
    "Mean total variation | Median | 95th percentile |",
    "|---:|---:|---:|---:|---:|---:|",
]
for label, diagnostic in association.items():
    if diagnostic["track_memberships"]:
        lines.append(
            f"| {label[1:]}° | {diagnostic['track_memberships']:,} | "
            f"{diagnostic['most_probable_candidate_changes']} | "
            f"{diagnostic['mean_total_variation']:.6f} | "
            f"{diagnostic['median_total_variation']:.3g} | "
            f"{diagnostic['p95_total_variation']:.6f} |"
        )
    else:
        lines.append(
            f"| {label[1:]}° | 0 | Unavailable | Unavailable | Unavailable | Unavailable |"
        )
lines += [
    "",
    "[Per-panel association diagnostics](association-diagnostic.json) retain the "
    "denominators. Small weight changes explain limited reassociation, but do not "
    "validate the existing candidate assignments or establish why they are concentrated.",
    "",
    "## Numerical evidence and retained failures",
    "",
    f"{sum(a.get('qualified', False) for _, a in starts)}/{len(starts)} optimizer starts "
    "qualify. Selection uses training score only, never reference error. All 72 "
    "baseline-derived starts reproduce the no-cone score, gradient and held rows. "
    "Initial synthetic tests cover neutral equivalence, derivatives, held-data isolation "
    "and receiver symmetry; a separate independent Student-t calculation verifies "
    "the conditional held-density algebra for all four widths.",
    "",
    f"{len(jobs)} process receipts: {sum(j['exit_code'] == 0 for j in jobs)} exit zero. "
    f"Total job wall time {sum(j['wall_s'] for j in jobs):.2f} s, "
    f"maximum {max(j['wall_s'] for j in jobs):.2f} s, "
    f"peak RSS {max(j['max_rss_kib'] for j in jobs):,} KiB. "
    "Process success is distinct from scientific qualification and selected-fit audit success.",
    "",
]
for r in rows:
    if not r["validated"]:
        lines.append(
            f"- **{r['unit']}**: selected-fit audit failed or unavailable; "
            "excluded from complete medians, retained in planned denominator."
        )
        path = HERE / "runs" / r["unit"] / "held/result.json"
        if path.exists():
            audit = json.loads(path.read_text())
            for c in audit["gradient_checks"]:
                if not c["passed"]:
                    lines.append(
                        f"  - Parameter {c['axis']}: "
                        f"maximum derivative discrepancy "
                        f"{max(s['absolute_difference'] for s in c['steps']):.6g}; "
                        f"grid crossing: {any(s['crosses_grid_node'] for s in c['steps'])}."
                    )
if len(valid) == 72:
    lines.append("All selected-fit audits pass.")
if list(HERE.glob("runs/**/recovery.json")):
    lines += [
        "",
        "The c30 fit launcher stopped with exit 143; its cause was not established. "
        "Its final child had completed with GNU time exit status 0 before the launcher "
        "wrote the exit receipt. That receipt was recovered from saved evidence, and "
        "only the twelve unstarted fits were launched with identical commands and "
        "limits. No completed fit was rerun. The c30 batch report links the recovery "
        "record and continuation code. The launcher interruption remains distinct "
        "from the child process receipts and scientific qualification failures.",
    ]
lines += [
    "",
    "No failed optimizer start or audit was retried, removed or reclassified. "
    "Each batch report lists its unqualified starts and all eighteen panel outcomes:",
    "",
    *[
        f"- [{k[1:]}° results](RESULTS-{k}.md), [complete data](summary-{k}.json), "
        f"[resource receipts](resources-{k}.json)."
        for k in LABELS
    ],
    "",
    "## Interpretation and next tests",
    "",
    "The scan-wide cone constraint is now exercised in a joint position model. "
    "No width is selected from these exposed reference errors. The unsurveyed "
    "reference, assumed world pose, retained candidate bank and previously explored "
    "single-site panels limit conclusions: nominal sub-km cases do not establish "
    "blind accuracy or calibrated confidence. Widths are sensitivity arms, not fitted "
    "hardware beamwidths. Wider cones can be geometrically feasible without adding "
    "enough directional information to improve location.",
    "",
    "Next priorities are shared pose/beam uncertainty with independent calibration, "
    "an explicit unassociated-track alternative and a reception/non-reception "
    "likelihood that retains clutter, and independently "
    "validated cross-RX track associations to constrain travel direction. Any future "
    "cone-plus-receiver-timing experiment must be separately frozen and evaluated; "
    "this report does not combine those models. The partial-timing s050/s200 studies "
    "remain pending, and [s010](../2026_09_29_partial_receiver_timing/RESULTS-s010.md) "
    "is a separate completed batch.",
    "",
    "[Protocol](PROTOCOL.md), [frozen plan](plan.json), [initial tests](tests.log), "
    "[independent predictive test](predictive-tests.log), and "
    "[hash inventory](evidence-sha256.json) provide reproduction evidence. Run tests "
    "and prepare once, then fit, held audit, summarize and write_batch_report for "
    "c20/c30/c40/c50 in order; write_report assembles and seals the completed study. "
    "Existing run directories are immutable evidence. One bounded worker used cached "
    "inputs; no RF collection, waveform reads, propagation or provider fetches.",
    "",
]
(HERE / "README.md").write_text("\n".join(lines))
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("runs/**/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest, name
        if name not in bindings:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        bindings[name] = digest
for path in HERE.rglob("*"):
    if path.is_file() and "__pycache__" not in path.parts and path.name != "evidence-sha256.json":
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
(HERE / "evidence-sha256.json").write_text(
    json.dumps(dict(sorted(bindings.items())), indent=2) + "\n"
)
print(json.dumps({"validated": len(valid), "planned": len(rows), "bindings": len(bindings)}))
