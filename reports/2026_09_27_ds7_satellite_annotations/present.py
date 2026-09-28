"""Create a local searchable annotation table and scientific sky plot."""
# ruff: noqa: E501 -- Embedded HTML/JavaScript is rendered as a standalone artifact.

import json
from collections import Counter
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    out = Path(__file__).parent / "local"
    rows = json.loads((out / "track-annotations.json").read_text())
    candidates = json.loads((out / "top-three-candidates.json").read_text())
    lookup = {}
    for c in candidates:
        lookup.setdefault((c["session_id"], c["track_id"]), []).append(c)
    for row in rows:
        row["alternatives"] = lookup.get((row["session_id"], row["track_id"]), [])
    # Link previously studied raw-bit excerpts through actual track visit membership.
    requested = {
        "scan-fw-a2d5dadd1a63c960": [191, 208],
        "scan-fw-a40658642d9ade6a": [2022],
        "scan-fw-0da0bd80eeec99cf": [947],
    }
    by_track = {(r["session_id"], r["track_id"]): r for r in rows}
    links = []
    for item in json.loads((out / "inputs.json").read_text())["recordings"]:
        sid = item["session_id"]
        if sid in requested:
            for track in json.loads(Path(item["tracks"]).read_text())["tracks"]:
                for visit in requested[sid]:
                    if visit in track["visits"]:
                        links.append(dict(visit=visit, **by_track[(sid, track["track_id"])]))
    (out / "recovered-signal-track-links.json").write_text(json.dumps(links, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, subplot_kw={"projection": "polar"}, figsize=(12, 6))
    for rx, ax in enumerate(axes):
        chosen = [r for r in rows if r["receiver_id"] == rx and r["status"] == "likely_conditional"]
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_xticks(
            np.radians(np.arange(0, 360, 45)), ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        )
        ax.scatter(
            np.radians([r["azimuth_mid_deg"] for r in chosen]),
            [90 - r["elevation_mid_deg"] for r in chosen],
            s=8,
            alpha=0.35,
        )
        ax.set_ylim(0, 90)
        ax.set_yticks([0, 30, 60, 90], ["90°", "60°", "30°", "0°"])
        ax.set_title(
            f"Software RX{rx}: {len(chosen):,} conditional likely tracks\n"
            f"Provisional connector RX{rx + 1}: {'west' if rx == 0 else 'east'} azimuth",
            pad=24,
        )
    fig.suptitle("DS7 satellite directions at track midpoint · roof site 37.849056°N, 122.485755°W")
    fig.text(
        0.5,
        0.025,
        "Doppler-ranked shortlist matches, not decoded identities. "
        "Pointing elevation and beam pattern unknown; no directional exclusion applied.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 0.93))
    fig.savefig(out / "receiver-sky-matches.png", dpi=170)
    data = json.dumps(rows).replace("<", "\\u003c")
    counts = dict(Counter(r["status"] for r in rows))
    html = """<!doctype html><meta charset="utf-8"><title>DS7 satellite annotations</title>
<style>body{font:15px system-ui;margin:32px;color:#172735;background:#f6f8fa}h1{margin-bottom:8px}
input,select,button{padding:8px;margin:6px}table{border-collapse:collapse;background:white;width:100%}
td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left;font-size:13px}th{position:sticky;top:0;background:#e6edf3}
small{color:#526477}details{max-width:400px}img{max-width:100%}</style>
<h1>DS7 track ↔ Starlink candidates</h1>
<p>88 recordings · 5,142 exported tracks · known roof site 37.849056°N, 122.485755°W.</p>
<p>Conditional Doppler associations within frozen candidate shortlists. No decoded IDs.
Unknown antenna elevation/beam pattern; provisional RX0 west / RX1 east mapping.
“Likely” is a diagnostic rule, not a calibrated probability. Raw and derived data remain local.</p>
<p id="summary"></p><input id="query" placeholder="Satellite, NORAD, session or track" size="45">
<select id="status"><option value="">All statuses</option><option>likely_conditional</option><option>tentative</option>
<option>unresolved_poor_fit</option><option>unresolved_no_candidate_bank</option></select>
<select id="rx"><option value="">Both receivers</option><option value="0">RX0</option><option value="1">RX1</option></select>
<button id="prev">Previous</button><button id="next">Next</button><span id="count"></span>
<table><thead><tr><th>Track / session</th><th>UTC start</th><th>RX / channel</th><th>Status</th>
<th>Top candidate</th><th>Validation RMS Hz</th><th>Train margin Hz</th><th>Az / el</th><th>Alternatives</th></tr></thead><tbody id="body"></tbody></table>
<script>const rows=DATA; let page=0;const $=id=>document.getElementById(id);
$('summary').textContent=SUMMARY;function render(){const q=$('query').value.toLowerCase();
const filtered=rows.filter(r=>(!$('status').value||r.status===$('status').value)&&
(!$('rx').value||String(r.receiver_id)===$('rx').value)&&
(!q||[r.session_id,r.track_id,r.satellite_name,r.norad_id].join(' ').toLowerCase().includes(q)));
page=Math.max(0,Math.min(page,Math.ceil(filtered.length/100)-1));$('body').replaceChildren();
for(const r of filtered.slice(page*100,page*100+100)){const tr=document.createElement('tr');
const fmt=n=>n==null?'—':n.toFixed(1);for(const value of [r.track_id.slice(7,19)+' / '+r.session_id,
r.start_utc,r.receiver_id+' / '+r.channel,r.status,(r.satellite_name||'Unresolved')+' '+(r.norad_id||''),
fmt(r.validation_rms_hz),fmt(r.runner_up_margin_hz),fmt(r.azimuth_mid_deg)+' / '+fmt(r.elevation_mid_deg)]){
const td=document.createElement('td');td.textContent=value;tr.append(td)}
const td=document.createElement('td'),d=document.createElement('details'),s=document.createElement('summary');
s.textContent='Top '+r.alternatives.length;d.append(s);for(const c of r.alternatives){const p=document.createElement('p');
p.textContent=c.rank+'. '+c.satellite_name+' (NORAD '+c.norad_id+'), validation '+fmt(c.validation_rms_hz)+' Hz';d.append(p)}
td.append(d);tr.append(td);$('body').append(tr)}$('count').textContent=filtered.length+' tracks · page '+(page+1);}
for(const id of ['query','status','rx'])$(id).oninput=()=>{page=0;render()};
$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render()};render();</script>"""
    html = html.replace("const rows=DATA", "const rows=" + data)
    html = html.replace("=SUMMARY", "=" + json.dumps(str(counts)))
    (out / "annotations.html").write_text(html)


if __name__ == "__main__":
    main()
