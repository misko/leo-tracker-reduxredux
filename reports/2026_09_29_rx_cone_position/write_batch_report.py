"""Render a completed width batch without treating it as the full grid result."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
label = sys.argv[1]
assert label in ("c20", "c30", "c40", "c50")
summary = json.loads((HERE / f"summary-{label}.json").read_text())
resources = json.loads((HERE / f"resources-{label}.json").read_text())
rows = summary["rows"]
assert len(rows) == 18
valid = [r for r in rows if r["validated"]]
alternatives = [(r["unit"], a) for r in rows for a in r["alternatives"]]
geo_improved = sum(r["error_m"] < r["baseline_error_m"] for r in valid)
held_improved = sum(r["held_gain"] > 0 for r in valid)
qualified = sum(a.get("qualified", False) for _, a in alternatives)


def number(value):
    return "Incomplete" if value is None else f"{value:,.3f}"


lines = [
    f"# {label[1:]}-degree half-angle: joint location batch",
    "",
    "This is one predeclared width batch, not a completed comparison of all four widths. "
    "No width is selected from reference errors. Cone axes and widths remain fixed across "
    "every track in a panel; the fitted parameters are position and recording timings.",
    "",
    f"**{len(valid)}/18 selected fits pass the audit.** "
    f"Among passing panels, geography improves in {geo_improved}/{len(valid)} "
    f"and matched held Doppler prediction improves in {held_improved}/{len(valid)}. "
    "Failed panels remain in the planned denominator; partial-subset medians are separately "
    "labeled in the JSON and are not substituted for complete medians below.",
    "",
    "| Dataset | Scans | Audited / planned | Cone median error (m) | Sub-km audited sets |",
    "|---|---:|---:|---:|---:|",
]
for a in summary["aggregates"]:
    lines.append(
        f"| {a['dataset']} | {a['size']} | {a['validated']}/{a['planned']} | "
        f"{number(a['median_error_m'])} | {a['subkm']} |"
    )
lines += [
    "",
    "Medians are across joint scan-set estimates, not independent single scans.",
    "",
    f"![All panel comparisons](comparison-{label}.png)",
    "",
    "| Panel | Baseline error (m) | Cone error (m) | Held change (nats) | Audited |",
    "|---|---:|---:|---:|---|",
]
for r in rows:
    error = number(r.get("error_m"))
    gain = f"{r['held_gain']:+.3f}" if "held_gain" in r else "Unavailable"
    if not r["validated"]:
        error += " (unvalidated)"
        gain += " (unvalidated)"
    lines.append(
        f"| {r['panel_id']} | {r['baseline_error_m']:,.3f} | {error} | {gain} | "
        f"{'Pass' if r['validated'] else 'Failed / unavailable'} |"
    )
lines += [
    "",
    "Training-only selection and retained failures:",
    "",
    f"- {qualified}/{len(alternatives)} optimizer starts qualify.",
    f"- {len(summary['no_cone_validations'])}/18 baseline-derived starts "
    "reproduce the saved no-cone model.",
    f"- Scoring verifies {summary['execution_bindings_verified']:,} execution/input bindings.",
    f"- Job wall time {resources['total_job_wall_s']:.2f} s; "
    f"maximum {resources['max_job_wall_s']:.2f} s; "
    f"peak RSS {resources['max_rss_kib']:,} KiB.",
]
for unit, a in alternatives:
    if not a.get("qualified", False):
        lines.append(
            f"- Retained unqualified start: {unit} / {a['start']}: "
            f"{a.get('message', a.get('exit_code'))}."
        )
recoveries = list(HERE.glob(f"runs/*_{label}/fit/*/recovery.json"))
for path in recoveries:
    recovery = json.loads(path.read_text())
    lines += [
        "",
        f"Administrative interruption: launcher session {recovery['launcher_session']} "
        f"stopped with exit {recovery['launcher_exit_code']} (cause not established). "
        f"The child {recovery['completed_child']} had already completed with GNU time "
        "exit status 0 and a completion log. Its missing exit receipt and seal were "
        "recovered from that evidence. The twelve unstarted fits then continued with "
        "identical commands and resource limits. No completed fit was rerun. "
        f"[Recovery evidence]({path.relative_to(HERE)}) and "
        "[continuation code](resume_c30.py) preserve the interruption separately "
        "from scientific fit failures.",
    ]
lines += [
    "",
    "The factor has a fixed 2-degree soft edge and 1% floor; it is not a calibrated "
    "beam or clutter likelihood. Held scores condition on training cone compatibility and "
    "do not score held detections or impose hard held-cone membership. Swapped/co-pointed "
    "controls in the JSON are evaluated at the nominal fitted point without refitting.",
    "",
    "The exposed unsurveyed reference and dependent, previously explored single-site panels "
    "do not establish blind accuracy or calibrated sub-km resolution.",
    "",
    f"See [protocol](PROTOCOL.md), [batch evidence](summary-{label}.json), "
    f"[receipts](resources-{label}.json), [initial tests](tests.log), and "
    "[independent conditional-density test](predictive-tests.log). "
    "No retries, outcome-based exclusions or relaxed gates are used.",
    "",
]
(HERE / f"RESULTS-{label}.md").write_text("\n".join(lines))
print("Wrote", HERE / f"RESULTS-{label}.md")
