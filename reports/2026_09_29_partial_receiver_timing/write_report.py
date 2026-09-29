"""Assemble the three completed, predeclared timing-regularization strengths."""

import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LABELS = ("s010", "s050", "s200")
summaries = {k: json.loads((HERE / f"summary-{k}.json").read_text()) for k in LABELS}
resources = {k: json.loads((HERE / f"resources-{k}.json").read_text()) for k in LABELS}
rows = [r for s in summaries.values() for r in s["rows"]]
assert len(rows) == 54 and len({r["unit"] for r in rows}) == 54
assert all(len(s["rows"]) == 18 for s in summaries.values())
neutral_checks = sum(len(s["nested_validations"]) for s in summaries.values())
valid = [r for r in rows if r["validated"]]
starts = [a for r in rows for a in r["alternatives"]]
jobs = [j for r in resources.values() for j in r["jobs"]]


def number(v):
    return "Incomplete" if v is None else f"{v:,.0f}"


def aggregate(label, ds, size):
    return next(
        a for a in summaries[label]["aggregates"] if a["dataset"] == ds and a["size"] == size
    )


def baseline(ds, size, key):
    values = []
    for s in summaries.values():
        values.append(sorted(r[key] for r in s["rows"] if r["dataset"] == ds and r["size"] == size))
    assert all(v == values[0] for v in values) and len(values[0]) == 3
    return statistics.median(values[0])


fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
for ax, size in zip(axes, (4, 8), strict=True):
    for ds, color in zip(("DS7", "DS8", "DS9"), ("#0072B2", "#D55E00", "#009E73"), strict=True):
        points = [aggregate(k, ds, size)["median_error_m"] for k in LABELS]
        ax.plot(
            [0.1, 0.5, 2],
            [v if v is not None else float("nan") for v in points],
            "o-",
            color=color,
            label=ds,
        )
        ax.axhline(baseline(ds, size, "baseline_error_m"), color=color, linestyle=":", alpha=0.5)
    ax.axhline(1000, color="black", linestyle="--", linewidth=1, label="1 km")
    ax.set(
        title=f"{size} consecutive scans",
        xlabel="Timing-difference penalty scale (s)",
        xscale="log",
    )
    ax.set_xticks([0.1, 0.5, 2], ["0.1", "0.5", "2.0"])
    ax.grid(alpha=0.2)
axes[0].set_ylabel("Median joint-set position error (m)")
axes[1].legend()
fig.suptitle(
    "Partial receiver-timing pooling · dotted lines: one-timing baseline\n"
    "Gaps indicate incomplete audits; three sets per dataset / size"
)
fig.tight_layout()
for ext in ("png", "svg"):
    fig.savefig(HERE / f"timing-strength-comparison.{ext}", dpi=160)

lines = [
    "# Partial pooling of receiver timing differences: complete sensitivity study",
    "",
    "**Do not promote timing regularization as a reliable sub-km solution.** "
    "Every complete DS7 and DS8 median remains above 1 km at both scan-set sizes. "
    "The audited late DS9 eight-scan errors remain above 3.7 km. Held prediction "
    "improves more often than geography, so predictive gains alone do not resolve "
    "the location problem. No strength is selected from these reference errors.",
    "",
    "The frozen 0.1-, 0.5-, and 2-second regularization batches are complete. "
    "Each fits one position and separate RX0/RX1 timings per recording, penalizing "
    "deviations of each RX timing difference from its fitted common mean. The mean "
    "is unpenalized; this does not impose zero receiver delay. The scales are "
    "sensitivity arms, not calibrated timing uncertainties or reference-selected winners.",
    "",
    f"**{len(valid)}/54 selected solutions pass the numerical audit.** "
    f"Among passing solutions, {sum(r['error_m'] < r['baseline_error_m'] for r in valid)} "
    f"improve position error and {sum(r['held_gain'] > 0 for r in valid)} improve held "
    "Doppler prediction versus one timing per recording. These counts include "
    "dependent arms and nested windows; they are not independent trials.",
    "",
    "Median error in metres across early/middle/late joint scan-set estimates. "
    "A full median requires all three selected fits to pass. Single-scan accuracy "
    "is not measured by these tables.",
    "",
    "| Scans | Model / penalty scale | DS7 | DS8 | DS9 |",
    "|---:|---|---:|---:|---:|",
]
for size in (4, 8):
    for title, key in (
        ("One timing per scan", "baseline_error_m"),
        ("Independent RX timings", "free_timing_error_m"),
    ):
        values = [baseline(ds, size, key) for ds in ("DS7", "DS8", "DS9")]
        lines.append(f"| {size} | {title} | " + " | ".join(map(number, values)) + " |")
    for label in LABELS:
        values = [aggregate(label, ds, size)["median_error_m"] for ds in ("DS7", "DS8", "DS9")]
        scale = summaries[label]["rows"][0]["sigma_s"]
        lines.append(
            f"| {size} | Partial pooling: {scale} s | " + " | ".join(map(number, values)) + " |"
        )
lines += [
    "",
    "![Timing-strength comparison](timing-strength-comparison.png)",
    "",
    "| Scale | Audited / planned | Lower error vs one timing | Better held vs one timing | "
    "Lower error vs independent RX | Better held vs independent RX | Audited sub-km sets |",
    "|---:|---:|---:|---:|---:|---:|---:|",
]
for s in summaries.values():
    v = [r for r in s["rows"] if r["validated"]]
    lines.append(
        f"| {s['rows'][0]['sigma_s']} s | {len(v)}/18 | "
        f"{sum(r['error_m'] < r['baseline_error_m'] for r in v)}/{len(v)} | "
        f"{sum(r['held_gain'] > 0 for r in v)}/{len(v)} | "
        f"{sum(r['error_m'] < r['free_timing_error_m'] for r in v)}/{len(v)} | "
        f"{sum(r['held_gain_vs_free'] > 0 for r in v)}/{len(v)} | "
        f"{sum(r['error_m'] < 1000 for r in v)} |"
    )
lines += [
    "",
    "The recurring late DS9 eight-scan case remains in all planned denominators:",
    "",
    "| Scale | Late DS9 eight-scan error (m) | Audit |",
    "|---:|---:|---|",
]
for s in summaries.values():
    r = next(r for r in s["rows"] if r["panel_id"] == "DS9_late_8")
    lines.append(
        f"| {r['sigma_s']} s | {number(r.get('error_m'))} | "
        f"{'Pass' if r['validated'] else 'Failed; value unvalidated'} |"
    )
lines += [
    "",
    "The same Student-t4/100 Hz shared-track scale likelihood, candidate banks, "
    "training/held split, offset prior, position bounds and timing bounds are retained. "
    "The penalty is subtracted only from the training objective; held scores contain "
    "no penalty. Raw training likelihood, penalty and penalized objective are recorded "
    "and verified separately. Training selects the highest qualified objective within "
    "each fixed scale, never a geographic winner or a cross-scale objective maximum.",
    "",
    f"{sum(a.get('qualified', False) for a in starts)}/{len(starts)} starts qualify. "
    f"{neutral_checks}/54 nested-baseline checks reproduce the tied model. The initial eight tests "
    "cover the penalty gradient, common-difference invariance and held-row preservation. "
    "Selected-fit audits replay objectives and use two finite-difference step sizes "
    "per parameter, retaining grid-crossing and derivative failures.",
    "",
    f"{len(jobs)} child process receipts; {sum(j['exit_code'] == 0 for j in jobs)} "
    f"exit zero. Total job wall time {sum(j['wall_s'] for j in jobs):.2f} s, "
    f"maximum {max(j['wall_s'] for j in jobs):.2f} s, "
    f"peak RSS {max(j['max_rss_kib'] for j in jobs):,} KiB. "
    "Child process exit is separate from optimizer qualification and audit success.",
    "",
]
for r in rows:
    if not r["validated"]:
        lines.append(
            f"- {r['unit']}: audit failed or unavailable; full aggregate remains incomplete."
        )
        audit_path = HERE / "runs" / r["unit"] / "held/result.json"
        if audit_path.exists():
            audit = json.loads(audit_path.read_text())
            for check in audit["gradient_checks"]:
                if not check["passed"]:
                    discrepancy = max(s["absolute_difference"] for s in check["steps"])
                    crossing = any(s["crosses_grid_node"] for s in check["steps"])
                    lines.append(
                        f"  - Parameter {check['axis']}: maximum derivative discrepancy "
                        f"{discrepancy:.6g}; interpolation-grid crossing: {crossing}."
                    )
pauses = sorted(HERE.glob("continuation-s*.json"))
if pauses:
    lines += [
        "",
        f"The launchers paused {len(pauses)} times before starting another job "
        "when available memory fell below the frozen 5 GiB headroom requirement. "
        "All completed fit and audit jobs were sealed; unstarted jobs continued only after the "
        "original threshold was met. "
        "No completed job was rerun and no numerical or resource gate was relaxed. "
        "Launcher exits are separate from child process receipts. "
        "[s050 fit continuation](continue_s050.py), "
        "[s050 audit continuation](continue_held_s050.py), "
        "[s200 continuation](continue_s200.py), "
        "[bounded memory supervisor](supervise_s200.py), "
        "and these pause records preserve "
        "the administrative interruptions:",
        "",
        *[f"- [{path.name}]({path.name})" for path in pauses],
    ]
lines += [
    "",
    "Every panel result, failed start, fitted common delay, residual dispersion, "
    "penalty and material generic-only initialization difference is retained in "
    "the batch reports:",
    "",
    *[
        f"- [{k} results](RESULTS-{k}.md), [data](summary-{k}.json), "
        f"[resources](resources-{k}.json)."
        for k in LABELS
    ],
    "",
    "The previously exposed, unsurveyed single-site reference limits interpretation. "
    "A sub-km median across three sets does not establish sub-km accuracy for every "
    "window, independent satellite identity, measured receiver delays or calibrated "
    "resolution. This is a timing-only study, separate from the "
    "[receiver-cone experiment](../2026_09_29_rx_cone_position/README.md). "
    "Any combined model requires a separately declared comparison.",
    "",
    "[Next-model proposal](NEXT-MODEL.md) describes a separate contrast-frequency "
    "control and the normalization questions for an unassociated-track branch. "
    "It is untested and contributes no result to this study.",
    "",
    "[Protocol](PROTOCOL.md), [plan](plan.json), [tests](tests.log) and "
    "[hash inventory](evidence-sha256.json) bind the study. Completed s010 execution "
    "evidence from the earlier published checkpoint is preserved. Run tests and "
    "prepare once, then fit, held, summarize and write_batch_report for each strength "
    "in declared order; write_report assembles and seals completed results. Existing "
    "run folders are immutable. One bounded worker used cached inputs only, without "
    "RF collection, waveform reads, propagation or provider fetches.",
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
