"""Build a local static review of the already-computed audit; no analysis changes."""
import html
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    evidence=json.loads((HERE/'orientation-evidence.json').read_text())
    audit=json.loads((HERE/'association-audit.json').read_text())
    parts=['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DS13 association review</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1300px;margin:32px auto;padding:0 20px;color:#18232d}
h1,h2{line-height:1.15}a{color:#00649b}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:13px}
td,th{padding:7px;text-align:right;border-bottom:1px solid #dbe1e5}th{background:#edf3f7;position:sticky;top:0}
.warning{background:#fff2d8;padding:18px;border-left:5px solid #cc7800}.flag{color:#a63100;font-weight:650}
.scroll{overflow:auto}.plots{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:800px){.plots{display:block}}
</style><h1>DS13 · saved top-response association review</h1>
<p>A and B are independent scans. No reassignment, satellite filtering, or orbit/calibration refitting was performed.</p>
<div class="warning"><b>Correction to the previous position analysis:</b> the center labeled “known roof” was
the Spinnaker restaurant display preset (37.858988, −122.478103), not the capture-bound operator roof
(37.849056280893684, −122.48575489722863). The two are 1,292.65 m apart. Residuals and orbit curves below
intentionally preserve their saved model reference. Sky geometry uses the capture-bound roof, with unknown altitude
approximated by zero ellipsoid height. Operator coordinates are not claimed to be surveyed ground truth.</div>
<h2>Previous minima, correctly referenced</h2><p>Only distances are re-expressed; scores, gradients and the original search disk have not been recomputed.</p>
<table><tr><th>Scan</th><th>RF model</th><th>Distance to operator roof</th></tr>''']
    for r in evidence['prior_minima_reexpressed']:
        parts.append(f"<tr><td>{r['scan']}</td><td>{r['arm']}</td><td>{r['minimum_relative_operator_roof_m']['distance_m']:.1f} m</td></tr>")
    parts.append('''</table><p>Consequently, the previous claim that c = 0 improves A’s position estimate is reversed.
<a href="orientation-evidence.json">Capture bindings and coordinate provenance</a>.</p>
<h2>Orbit plots</h2><p>Left: all retained top-response GLRT observations plus associated calibrated orbit curves.
Right: the same unassociated records only. One record per receiver/channel/20 ms probe; this is not every alternative hypothesis.
Curves are broken at alias wraps, visibility gaps and calibration-fold boundaries.</p>''')
    for s in 'AB':
        parts.append(f'<details><summary>Scan {s}: complete orbit plot</summary><a href="orbit-{s}-all.png"><img src="orbit-{s}-all.png" alt="Scan {s} orbit plot"></a></details><p>Receiver detail: <a href="orbit-{s}-RX0.png">{s} RX0</a> · <a href="orbit-{s}-RX1.png">{s} RX1</a></p>')
    parts.append('''<h2>Residual curvature and receiver direction</h2><p>Ratio = RMS after intercept + linear fit / RMS after intercept + linear + quadratic fit,
on the identical assigned samples. The primary table below also controls separate channel intercepts. Native Hz, unweighted in-sample OLS;
small or gappy tracks can overfit. Ratios above 1.1 flag structure, not a wrong identity. These are current ±600 Hz-gated top-response memberships,
not the older ±150 Hz pruned experiment.</p><div class="plots">
<a href="curvature-ratios.png"><img src="curvature-ratios.png" alt="All curvature ratios"></a>
<a href="receiver-pointing-audit.png"><img src="receiver-pointing-audit.png" alt="All receiver direction checks"></a></div>
<p>RX0 nominally faces west (270°); RX1 east (90°). The 40° is the included feed-axis angle, not beam width.
Nominal elevation is 70° assuming a level mount. Positive angle advantage means closer to the receiving axis;
negative means closer to the other receiver. Actual boresights/beam patterns are unmeasured and connector mapping is provisional.
Opposite hemisphere is not an exclusion rule, and missing assignments on the other receiver do not establish nondetection.</p>''')
    for scan in audit['scans']:
        s=scan['scan'];pointing={(r['satellite'],r['rx']):r for r in scan['all_pointing']}
        rows=sorted((r for r in scan['all_tracks'] if r['arm']=='fitted-c'),key=lambda r:-r['span_s'])
        parts.append(f"<h2>Scan {s} · all {len(rows)} satellite/receiver tracks</h2><p>{scan['assigned']:,}/{scan['top_windows']:,} assigned top-response windows; {scan['satellites']} satellites. {scan['channel_controlled_ratio_over_1_1']} tracks have channel-controlled ratio &gt; 1.1.</p>")
        parts.append(f'<p>Download <a href="{s}-track-residual-metrics.csv">full track metrics including matched c = 0</a>, <a href="{s}-channel-residual-metrics.csv">per-channel metrics</a>, <a href="{s}-satellite-residual-metrics.csv">per-satellite metrics</a>, <a href="{s}-pointing-metrics.csv">pointing metrics</a>.</p>')
        parts.append('<div class="scroll"><table><tr><th>Satellite / RX</th><th>n</th><th>Span s</th><th>Max gap s</th><th>Raw RMS Hz</th><th>+linear RMS Hz</th><th>+quad RMS Hz</th><th>Ratio</th><th>Opposite %</th><th>Median axis advantage °</th></tr>')
        for r in rows:
            p=pointing[r['satellite'],r['rx']];ratio=r['channel_controlled_ratio']
            values=[f"{r['satellite']} / RX{r['rx']}",str(r['n']),f"{r['span_s']:.1f}",f"{r['max_gap_s']:.1f}",
                f"{r['channel_controlled_raw_rms_hz']:.1f}",f"{r['channel_controlled_linear_rms_hz']:.1f}",
                f"{r['channel_controlled_quadratic_rms_hz']:.1f}",f'{ratio:.3f}' if ratio is not None else 'undefined',
                f"{p['wrong_hemisphere_pct']:.1f}",f"{p['median_own_axis_advantage_deg']:+.1f}"]
            parts.append('<tr>'+''.join(f'<td class="{"flag" if ((i==7 and ratio is not None and ratio>1.1) or (i==8 and p["wrong_hemisphere_pct"]==100)) else ""}">{html.escape(v)}</td>' for i,v in enumerate(values))+'</tr>')
        parts.append('</table></div>')
    parts.append('<p>Reproduction: <a href="association_audit.py">audit script</a> · <a href="make_orbit_examples.py">archive plotting adapter</a> · <a href="association-audit.json">full numerical receipt</a>. Reusable rendering inputs are in src/leo/presentation/orbit_plot.py; no storage or analyzer coupling was added.</p></html>')
    (HERE/'review.html').write_text('\n'.join(parts))


if __name__=='__main__':main()
