"""Document one completed predeclared partial-timing batch."""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
label = sys.argv[1]
assert label in ("s010", "s050", "s200")
summary = json.loads((HERE / f"summary-{label}.json").read_text())
resources = json.loads((HERE / f"resources-{label}.json").read_text())
rows = summary["rows"]
assert len(rows) == 18
valid = [r for r in rows if r["validated"]]
starts = [(r["unit"], a) for r in rows for a in r["alternatives"]]
sigma = {"s010": 0.1, "s050": 0.5, "s200": 2.0}[label]


def value(v):
    return "Incomplete" if v is None else f"{v:,.3f}"


lines = [
    f"# Partial receiver timing: sigma = {sigma} seconds",
    "",
    "This is one completed batch of the predeclared 0.1/0.5/2-second sensitivity "
    "study, not completion of all three strengths. One common location is fitted "
    "with separate RX0/RX1 timings per recording. A quadratic penalty shrinks "
    "recording-specific RX timing differences toward their fitted common mean. "
    "The mean is not shrunk toward zero. No strength is selected from reference error.",
    "",
    f"**{len(valid)}/18 selected solutions pass the audit.** Against the one-timing "
    f"baseline, {sum(r['error_m'] < r['baseline_error_m'] for r in valid)}/{len(valid)} "
    f"have lower location error and {sum(r['held_gain'] > 0 for r in valid)}/{len(valid)} "
    "improve matched held Doppler prediction. Against independent receiver timings, "
    f"the corresponding counts are "
    f"{sum(r['error_m'] < r['free_timing_error_m'] for r in valid)}/{len(valid)} and "
    f"{sum(r['held_gain_vs_free'] > 0 for r in valid)}/{len(valid)}. "
    "Held scores contain no regularization penalty.",
    "",
    "| Dataset | Scans | Audited / planned | One-timing median (m) | "
    "Independent RX median (m) | Partial-pooling median (m) | Audited sub-km sets |",
    "|---|---:|---:|---:|---:|---:|---:|",
]
for a in summary["aggregates"]:
    lines.append(
        f"| {a['dataset']} | {a['size']} | {a['validated']}/{a['planned']} | "
        f"{value(a['matched_baseline_median_error_m'])} | "
        f"{value(a['matched_free_median_error_m'])} | {value(a['median_error_m'])} | "
        f"{a['subkm']} |"
    )
lines += [
    "",
    "Medians are joint estimates across early/middle/late scan sets, not single-scan "
    "medians. Complete partial-pooling medians require all three selected fits to "
    "pass. Baseline columns use the matching validated subset if a batch is incomplete. "
    "Four-scan sets are nested within eight-scan sets.",
    "",
    f"![All panel comparisons](comparison-{label}.png)",
    "",
    "| Panel | One timing (m) | Independent RX (m) | Partial pooling (m) | "
    "Held gain vs one timing (nats) | Held gain vs independent RX (nats) | Audit |",
    "|---|---:|---:|---:|---:|---:|---|",
]
for r in rows:
    lines.append(
        f"| {r['panel_id']} | {value(r['baseline_error_m'])} | "
        f"{value(r['free_timing_error_m'])} | {value(r.get('error_m'))} | "
        f"{r.get('held_gain', float('nan')):+.3f} | "
        f"{r.get('held_gain_vs_free', float('nan')):+.3f} | "
        f"{'Pass' if r['validated'] else 'Failed; values unvalidated'} |"
    )
lines += [
    "",
    "Training selects the greatest penalized score among successful interior starts "
    "with gradient infinity norm at most 0.01. The raw likelihood, penalty, and "
    "penalized objective remain separately recorded and checked. Scores across "
    "different strengths are not a hyperparameter-selection criterion.",
    "",
    f"{sum(a.get('qualified', False) for _, a in starts)}/{len(starts)} starts qualify; "
    f"{len(summary['nested_validations'])}/18 tied-baseline checks pass. "
    f"Scoring verified {summary['execution_bindings_verified']:,} execution/input bindings. "
    f"The maximum selected-fit derivative discrepancy is "
    f"{max(r['max_gradient_discrepancy'] for r in valid):.6g}.",
    "",
    f"{len(resources['jobs'])} process receipts; "
    f"{sum(j['exit_code'] == 0 for j in resources['jobs'])} exit zero. "
    f"Total job wall time {resources['total_job_wall_s']:.2f} s, "
    f"maximum {resources['max_job_wall_s']:.2f} s, "
    f"peak RSS {resources['max_rss_kib']:,} KiB. "
    "Optimizer qualification and numerical audit success are separate from process exit.",
    "",
]
for unit, a in starts:
    if not a.get("qualified", False):
        lines.append(
            f"- Retained unqualified start: {unit} / {a['start']}: "
            f"{a.get('message', a.get('exit_code'))}."
        )
lines += [
    "",
    "No failed start or audit was retried, removed or reclassified.",
    "",
    "| Panel | Fitted mean RX1−RX0 (s) | RMS deviation from mean (s) | Penalty |",
    "|---|---:|---:|---:|",
]
for r in valid:
    lines.append(
        f"| {r['panel_id']} | {r['common_rx1_minus_rx0_s']:+.6f} | "
        f"{r['difference_rms_s']:.6f} | {r['penalty']:.6f} |"
    )
paired = summary["paired_held"]
lines += [
    "",
    "The additional baseline-derived start can find a different optimum. Below are "
    "panels where its selected penalized score exceeds the best generic start by "
    "more than 0.001 nats. Initialization is training-selected; a higher training "
    "score need not give lower reference error.",
    "",
    "| Panel | Selected minus generic training (nats) | "
    "Selected error (m) | Generic-only error (m) |",
    "|---|---:|---:|---:|",
]
for r in valid:
    g = r.get("generic_selected")
    if g and g["training_gap_to_selected"] < -0.001:
        lines.append(
            f"| {r['panel_id']} | {-g['training_gap_to_selected']:.6f} | "
            f"{r['error_m']:,.3f} | {g['error_m']:,.3f} |"
        )
lines += [
    "",
    "These timings are fitted nuisance parameters, not independent measurements "
    "of receiver clock offsets. Their dispersion is regularized, so it cannot be "
    "interpreted as a measured timing uncertainty.",
    "",
    f"On the same held observations in the first four scans, "
    f"{sum(p['eight_minus_four_held'] > 0 for p in paired)}/{len(paired)} audited "
    "eight-scan fits improve prediction over the four-scan fit. "
    f"The median change is "
    f"{statistics.median(p['eight_minus_four_held'] for p in paired):+.3f} nats.",
    "",
    "The exposed unsurveyed reference, dependent scan sets and previously explored "
    "single site do not establish blind sub-km accuracy. The late DS9 eight-scan "
    "result is retained in every relevant aggregate. This timing model is separate "
    "from the fixed receiver-cone experiment; no combined improvement is claimed.",
    "",
    f"[Complete batch data](summary-{label}.json), [receipts](resources-{label}.json), "
    "[protocol](PROTOCOL.md), [frozen plan](plan.json), and [tests](tests.log). "
    "Existing output directories are immutable evidence. One bounded worker used "
    "cached inputs only; no RF collection, waveform reads, propagation or provider fetches.",
    "",
]
(HERE / f"RESULTS-{label}.md").write_text("\n".join(lines))
print("Wrote", HERE / f"RESULTS-{label}.md")
