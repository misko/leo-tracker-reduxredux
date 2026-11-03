"""Comparable satellite statistics at the capture roof, on frozen hard memberships."""
import html
import json
import sys
from pathlib import Path

import numpy as np

from association_audit import digest, dump, interpolate_positions, polynomial_audit, sky_geometry, write_csv

HERE = Path(__file__).resolve().parent
BULK = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
OUT = HERE / 'satellite-statistics'


def summarize(scan, arm):
    sys.path.insert(0, str(BULK))
    from profile_top_2km import Engine
    from joint_inputs import _coordinates
    evidence = json.loads((HERE / 'orientation-evidence.json').read_text())
    attribution = json.loads((HERE / f'gradient-by-satellite/{scan}-{arm}.json').read_text())
    engine = Engine(scan, arm)
    x = np.array(attribution['roof_fit']['vector'])
    np.testing.assert_allclose(_coordinates(x[:2]), evidence['operator_roof_lat_lon'], atol=1e-9, rtol=0)
    engine.obj.base.deadline = float('inf')
    pred, visible, _ = engine.obj.base.predict(x[:engine.obj.size], with_jacobian=True)
    pred += (engine.obj.features @ x[engine.obj.size:])[:, None]
    errors = (engine.data.measured[:, None] - pred + 1 / 4.4e-6 / 2) % (1 / 4.4e-6) - 1 / 4.4e-6 / 2
    timing = engine.obj.base.state(x[:engine.obj.size])['total_shifts_s']
    d = np.load(HERE / f'{scan}-assigned-observations.npz')
    lookup = {int(r): i for i, r in enumerate(engine.data.original_rows)}
    rows = np.array([lookup[int(r)] for r in d['row_id']])
    gradients = {r['satellite']: r for r in attribution['rows']}
    output, receivers = [], []
    for sat in sorted(set(d['satellite'])):
        m = d['satellite'] == sat
        ids = rows[m]; rx = d['rx'][m]; t = d['time_s'][m]; ch = d['channel'][m]
        col = int(np.flatnonzero(engine.data.numbers == sat)[0]); residual = errors[ids, col]
        geometry = sky_geometry(interpolate_positions(engine.data.nodes, engine.data.position[col], t + timing[col]),
                                *evidence['operator_roof_lat_lon'], rx, evidence['nominal_axes_enu'])
        wrong = geometry['east_unit'] * np.where(rx == 0, -1, 1) < 0
        g = gradients[int(sat)]
        # Separate receiver slopes and channel intercepts; pool SSE, not RMS values.
        lin_sse = quad_sse = 0.
        record = dict(scan=scan, arm=arm, satellite=int(sat), n=int(m.sum()), span_s=float(np.ptp(t)),
                      wrong_n=int(wrong.sum()), wrong_pct=float(100 * wrong.mean()),
                      rms_hz=float(np.sqrt(np.mean(residual ** 2))),
                      gradient_strength=g['gradient_magnitude_per_100m'],
                      east_gradient=g['east_gradient_per_100m'], north_gradient=g['north_gradient_per_100m'],
                      aligned_pressure=g['pressure_along_total_downhill'],
                      soft_support=g['soft_association_support'])
        for r in (0, 1):
            q = rx == r
            record[f'rx{r}_n'] = int(q.sum())
            record[f'rx{r}_wrong_pct'] = float(100 * wrong[q].mean()) if q.any() else None
            record[f'rx{r}_rms_hz'] = float(np.sqrt(np.mean(residual[q] ** 2))) if q.any() else None
            if not q.any():
                continue
            metrics = polynomial_audit(t[q], residual[q], ch[q], True)
            lin_sse += q.sum() * metrics['linear_rms_hz'] ** 2
            quad_sse += q.sum() * metrics['quadratic_rms_hz'] ** 2
            receivers.append(dict(scan=scan, arm=arm, satellite=int(sat), rx=r,
                span_s=float(np.ptp(t[q])), wrong_pct=record[f'rx{r}_wrong_pct'],
                median_off_axis_deg=float(np.median(geometry['own_off_axis_deg'][q])),
                min_off_axis_deg=float(np.min(geometry['own_off_axis_deg'][q])),
                max_off_axis_deg=float(np.max(geometry['own_off_axis_deg'][q])),
                east_gradient=g[f'rx{r}_east_per_100m'], north_gradient=g[f'rx{r}_north_per_100m'],
                gradient_strength=float(np.hypot(g[f'rx{r}_east_per_100m'], g[f'rx{r}_north_per_100m'])),
                **metrics))
        record.update(linear_rms_hz=float(np.sqrt(lin_sse / m.sum())),
                      quadratic_rms_hz=float(np.sqrt(quad_sse / m.sum())),
                      linear_quadratic_ratio=float(np.sqrt(lin_sse / quad_sse)),
                      visible_n=int(visible[ids, col].sum()))
        output.append(record)
    return output, receivers


def render(rows):
    sections = []
    for arm in ('fitted-c', 'zero-c'):
        for scan in 'AB':
            body = []
            for r in sorted((r for r in rows if r['scan'] == scan and r['arm'] == arm), key=lambda r: -r['gradient_strength']):
                vals = [r['satellite'], f"{r['rx0_n']} / {r['rx1_n']}",
                        ' / '.join('—' if r[f'rx{i}_wrong_pct'] is None else f"{r[f'rx{i}_wrong_pct']:.0f}%" for i in (0, 1)),
                        f"{r['span_s']:.1f}", f"{r['rms_hz']:.1f}", f"{r['linear_rms_hz']:.1f}",
                        f"{r['quadratic_rms_hz']:.1f}", f"{r['linear_quadratic_ratio']:.3f}",
                        f"{r['gradient_strength']:.3f}", f"{r['aligned_pressure']:+.3f}"]
                body.append('<tr' + (' class="focus"' if r['satellite'] == 60412 else '') + '>' +
                            ''.join(f'<td>{html.escape(str(v))}</td>' for v in vals) + '</tr>')
            header = ['Satellite', 'Windows RX0 / RX1', 'Opposite hemisphere RX0 / RX1', 'Span (s)',
                      'RMS (Hz)', '+ linear (Hz)', '+ quadratic (Hz)', 'Linear/quad', 'Gradient strength', 'Aligned pressure']
            sections.append(f'<h2>Scan {scan} · {arm}</h2><table><thead><tr>' +
                            ''.join(f'<th>{h}</th>' for h in header) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table>')
    return '<!doctype html><meta charset="utf-8"><title>DS13 satellite statistics</title><style>body{font:16px system-ui;margin:35px;max-width:1450px;color:#18232c}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:right}th{background:#edf3f6;position:sticky;top:0}.focus{background:#fff2c9}h2{margin-top:45px}p{max-width:1100px;line-height:1.5}</style><h1>DS13 · satellite statistics at capture-bound roof</h1><p>Independent scans. Frozen fitted-c greedy + replacement memberships; one highest-response refined candidate per receiver/channel/20 ms window. These are window counts, not all alternative peaks. Counts and observations matched across RF arms.</p><p>Opposite hemisphere: east of zenith on west-pointing RX0, or west of zenith on east-pointing RX1. This is not a beam violation. Missing receiver: —. Geometry uses each arm’s roof-fit timing, nominal axes and capture coordinates.</p><p>RMS: native-Hz residual about zero, before extra detrending. Linear/quadratic diagnostics fit separate channel constants and separate receiver polynomials; pooled via sum of squared errors. In-sample diagnostics, not applied orbit corrections. Span includes gaps.</p><p>Gradient strength: magnitude of the satellite contribution to the profiled score gradient, in score units per 100 m. Uses all top windows and soft ownership, whereas RMS/counts use frozen hard assignments. Strength is not identity confidence or deletion benefit. Aligned pressure: signed projection along the total score gradient; positive reinforces its downhill direction, negative opposes it. Timing-prior contribution is separate and omitted from satellite rows.</p>' + ''.join(sections)


def main():
    OUT.mkdir(exist_ok=True)
    rows, receivers = [], []
    for scan in 'AB':
        for arm in ('fitted-c', 'zero-c'):
            r, t = summarize(scan, arm); rows.extend(r); receivers.extend(t)
    write_csv(OUT / 'satellites.csv', rows); write_csv(OUT / 'receiver-tracks.csv', receivers)
    (OUT / 'table.html').write_text(render(rows))
    sources = [Path(__file__), HERE / 'association_audit.py', HERE / 'orientation-evidence.json', BULK / 'profile_top_2km.py']
    for scan in 'AB':
        sources += [HERE / f'{scan}-assigned-observations.npz', BULK / f'position-top-2km/{scan}-profile-input.npz']
        sources += [HERE / f'gradient-by-satellite/{scan}-{arm}.json' for arm in ('fitted-c', 'zero-c')]
    dump(OUT / 'receipt.json', dict(sources={str(p): digest(p) for p in sources}, satellite_rows=len(rows), receiver_rows=len(receivers), scope=__doc__))
    for scan in 'AB':
        print('SCAN', scan)
        for r in sorted((r for r in rows if r['scan'] == scan and r['arm'] == 'fitted-c'), key=lambda r: -r['gradient_strength']):
            print(f"| {r['satellite']} | {r['rx0_n']} / {r['rx1_n']} | {r['wrong_pct']:.0f}% | {r['rms_hz']:.1f} | {r['gradient_strength']:.3f} |")


if __name__ == '__main__':
    main()
