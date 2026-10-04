"""Build offline HTML and companion Markdown from packaged evidence (stdlib only)."""
from __future__ import annotations
import base64
import csv
import gzip
import hashlib
import html
import io
import json
import re
from pathlib import Path
from render_markdown import markdown

HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads(gzip.decompress((HERE / "evidence" / f"{name}.json.gz").read_bytes()))


def table(headers, rows):
    cell = lambda x: html.escape(str(x))
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th scope="col">{cell(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{cell(v)}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def figure(name, caption, index):
    path = HERE / "assets" / f"{name}.png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<figure id="fig-{name}"><img loading="lazy" src="data:image/png;base64,{data}" alt="{html.escape(caption, quote=True)}"><figcaption><b>Figure {index}.</b> {html.escape(caption)}</figcaption></figure>'


def build():
    metrics = json.loads((HERE / "evidence/metrics.json").read_text())
    manifest = json.loads((HERE / "evidence/manifest.json").read_text())
    for item in manifest:
        if "packaged" in item:
            actual = hashlib.sha256((HERE / item["packaged"]).read_bytes()).hexdigest()
            if actual != item["packaged_sha256"]:
                raise ValueError(f"Evidence hash mismatch: {item['packaged']}")
    content = (HERE / "report.template.html").read_text()
    metadata = json.loads((HERE / "evidence/detector-provenance.json").read_text())
    content = content.replace("@@SCANS@@",table(["Scan", "Session ID", "Capture start (UTC)"],
        [[s["scan"],s["session_id"],s["capture_start_utc"]] for s in metadata["scans"]]))
    config = metadata["scan_A_configuration"]
    content = content.replace("@@CONFIG@@",table(["Saved Scan A detector setting", "Value"],
        [[key,config[key]] for key in ("analyzer_id","sample_rate_hz","probe_ms","probe_stride_ms","glrt64_margin_gate","maximum_acquisition_candidates","timing_refinement","decision_score")]))
    labels = {"original": "Original GLRT; corrected timing", "refined": "Refined GLRT; all candidates", "top": "T1-AT v1; refined top per window"}
    replay = [load(f"B-t1-at-v1-replay-{arm}")["summary"] for arm in ("fitted-c", "zero-c")]
    content = content.replace("@@B_REPLAY@@", table(
        ["Calibration", "Assigned / windows", "Coverage", "Unassigned", "Satellites", "Assigned RMS (Hz)", "Exact historical match"],
        [[r["arm"], f'{r["assigned"]:,} / {r["denominator"]:,}', f'{100*r["coverage"]:.2f}%',
          r["unassigned"], r["satellites"], f'{r["rms_hz"]:.1f}', r["exact_historical_stages_match"]] for r in replay]))
    rows = []
    for r in metrics["results"]:
        rows.append([r["scan"], labels[r["stage"]], r["arm"], f'{r["assigned"]:,} / {r["denominator"]:,}',
                     f'{100*r["coverage"]:.2f}%', r["unassigned"], r["satellites"], int(r["objective"]), f'{r["assigned_rms_hz"]:.1f}'])
    content = content.replace("@@RESULTS@@", table(["Scan", "Observation set", "Calibration", "Assigned / denominator", "Coverage", "Unassigned", "Satellites", "Objective", "Assigned RMS (Hz)"], rows))
    rows = [[r["scan"], labels[r["stage"]], r["arm"], r["greedy_assigned"], r["assigned"], r["replacement_trials"], r["accepted"], f'{r["elapsed_s"]:.2f}'] for r in metrics["results"]]
    content = content.replace("@@SEARCH@@", table(["Scan", "Observation set", "Calibration", "Greedy assigned", "After replacement", "Removal trials", "Accepted", "Selection wall time (s)"], rows))
    cutoffs = load("margin-cutoffs")["summaries"] + [load("margin-06")]
    content = content.replace("@@CUTOFFS@@", table(["Refined-margin cutoff", "Candidates", "Multi-candidate windows", "Within-window pairs", "Pairs <50 Hz", "Pairs ≥1 kHz"],
        [[r["cutoff"], r["candidates"], r["multi_candidate_probes"], r["pairs"], f'{100*sum(r["counts"][:2])/r["pairs"]:.1f}%', f'{100*r["counts"][-1]/r["pairs"]:.1f}%'] for r in cutoffs]))
    content = content.replace("@@POOLS@@", table(["Experiment", "Archived catalog IDs", "Matched timing hypotheses / arm", "Discovery wall time (s)"],
        [[p["key"], p["catalog_ids"], p["matched_modes"], f'{p["discovery_s"]:.1f}'] for p in metrics["pools"]]))
    content = content.replace("@@TRACKS@@", table(["Calibration", "NORAD", "Windows", "Absolute timing shift (s)", "Assigned RMS (Hz)"],
        [[arm, s["catalog_number"], s["count"], f'{s["offset_s"]:+.6f}', f'{s["rms_hz"]:.2f}']
         for arm in ("fitted-c", "zero-c") for s in sorted(load(f"A-top-{arm}")["final"]["selected"], key=lambda s: -s["count"])]))
    content = content.replace("@@PROVENANCE@@", table(["Packaged file / source", "SHA-256", "Role"],
        [[p.get("packaged", p.get("source")), p.get("packaged_sha256", p.get("sha256")), p["kind"]] for p in manifest]))
    # Measurements and receipts remain accessible even if only this HTML travels.
    downloads = []
    for p in sorted((HERE / "evidence").iterdir()):
        mime = "application/gzip" if p.suffix == ".gz" else "application/json"
        data = base64.b64encode(p.read_bytes()).decode()
        downloads.append(f'<li><a download="{p.name}" href="data:{mime};base64,{data}">{p.name}</a> <span class="muted">({p.stat().st_size:,} bytes)</span></li>')
    content = content.replace("@@DOWNLOADS@@", '<ul class="downloads">' + ''.join(downloads) + '</ul>')
    sources = []
    for p in sorted((HERE / "sources").glob("*.py")):
        data = base64.b64encode(p.read_bytes()).decode()
        sources.append(f'<li><a download="{p.name}" href="data:text/plain;base64,{data}">{p.name}</a></li>')
    content = content.replace("@@SOURCES@@", '<ul class="downloads">' + ''.join(sources) + '</ul>')
    counter = 0
    def replace(match):
        nonlocal counter
        counter += 1
        return figure(match[1], match[2], counter)
    content = re.sub(r"@@FIG\[([^|]+)\|([^\]]+)\]@@", replace, content)
    if "@@" in content:
        raise ValueError("Unresolved template placeholder")
    (HERE / "report.html").write_text(content)
    (HERE / "report.md").write_text(markdown(content))
    return counter


if __name__ == "__main__":
    print(f"Built report.html and report.md with {build()} figures and downloadable evidence.")
