"""Tables and static figures for the frozen-ranking position experiment."""
import csv
import html
import json
from pathlib import Path

import numpy as np
from association_audit import digest

HERE = Path(__file__).resolve().parent
OUT = HERE / 'subset-position-search'
NAMES = {'rms': 'Lowest satellite RMS', 'support': 'Most windows per satellite', 'glrt': 'Highest window GLRT score'}


def main():
    rows = []
    for scan in 'AB':
        subsets = json.loads((OUT / f'{scan}-subsets.json').read_text())['cases']
        for subset in subsets:
            for arm in ('fitted-c', 'zero-c'):
                source = OUT / f'{scan}-{subset["case_id"]}-{arm}.json'
                if not source.exists():
                    continue
                r = json.loads(source.read_text()); g = r['gradient_per_100m']
                trials = np.array([t['point_km'] for t in r['trials']])
                disagreement = float(np.max(np.linalg.norm(trials - trials[0], axis=1)) * 1000)
                rows.append(dict(scan=scan, ranking=subset['method'], fraction=subset['fraction'], arm=arm,
                    windows=subset['n_windows'], candidates=subset['n_candidates'], owners=subset['n_owners'],
                    rx0_windows=subset['rx_counts'][0], rx1_windows=subset['rx_counts'][1],
                    distance_m=r['distance_m'], east_m=r['east_m'], north_m=r['north_m'],
                    east_gradient_per_100m=g[0], north_gradient_per_100m=g[1],
                    gradient_strength=r['gradient_strength'],
                    gradient_strength_per_1000_windows=r['gradient_strength_per_1000_windows'],
                    delta_score=r['delta_score'], delta_score_per_window=r['delta_score'] / subset['n_windows'],
                    boundary_limited=r['boundary_limited'], successful_starts=r['successful_starts'],
                    ambiguity=bool(disagreement > 100 or r['successful_starts'] < 3),
                    polish_unconverged=bool(r.get('cross_restart_audit', {}).get('polished') and
                        not r['cross_restart_audit']['polished']['success']),
                    lower_point_after_neighbors=r.get('cross_restart_audit', {}).get('lower_point_after_neighbors', False),
                    start_spread_m=disagreement, minimum_neighbor_delta=r['minimum_neighbor_delta'],
                    gradient_fd_error=float(np.max(abs(np.array(g) - r['gradient_fd_10m']))),
                    roof_data_nll=r['roof']['data_nll'], best_data_nll=r['best']['data_nll'],
                    roof_prior_nll=r['roof']['prior_nll'], best_prior_nll=r['best']['prior_nll'],
                    best_nearest_rms_inside600_hz=r['best']['nearest_rms_inside600_hz'],
                    source=source.name))
    with (OUT / 'summary.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for key, label, filename in [('distance_m', 'Best-found distance from roof (m)', 'minimum-distance.png'),
            ('gradient_strength', 'Roof gradient magnitude\n(score change per 100 m)', 'roof-gradient.png'),
            ('gradient_strength_per_1000_windows', 'Roof gradient magnitude / 100 m\nper 1,000 retained windows', 'normalized-gradient.png')]:
        fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharex=True, sharey=True)
        for i, scan in enumerate('AB'):
            for j, method in enumerate(NAMES):
                ax = axes[i, j]
                for arm, color in [('fitted-c', '#0072b2'), ('zero-c', '#d55e00')]:
                    rr = sorted((r for r in rows if r['scan'] == scan and r['ranking'] == method and r['arm'] == arm), key=lambda r: r['fraction'])
                    x = [r['fraction'] * 100 for r in rr]; y = [r[key] for r in rr]
                    ax.plot(x, y, 'o-', color=color, label='Fitted c' if arm == 'fitted-c' else 'c = 0')
                    for r, xx, yy in zip(rr, x, y):
                        if r['boundary_limited']:
                            ax.plot(xx, yy, '^', ms=10, color=color, mec='black')
                        elif r['ambiguity'] or r['polish_unconverged'] or r['lower_point_after_neighbors']:
                            ax.plot(xx, yy, '*', ms=13, color=color, mec='black')
                        if key == 'distance_m':
                            peer = next(q for q in rows if q['scan'] == scan and q['ranking'] == method and
                                        q['fraction'] == r['fraction'] and q['arm'] != arm)
                            above = yy >= peer[key]
                            ax.annotate(f'{yy:.0f}', (xx, yy), xytext=(0, 9 if above else -17), textcoords='offset points', ha='center', fontsize=8, color=color)
                ax.set_title(f'Scan {scan}\n{NAMES[method]}', fontsize=11); ax.grid(alpha=.2)
                ax.set_xticks([25, 50, 75, 100]); ax.set_xlim(20, 105)
                ax.set_xlabel('Top fraction retained (%)')
                if j == 0:
                    ax.set_ylabel(label)
                if key == 'distance_m':
                    ax.set_ylim(-70, 2150); ax.axhline(2000, color='.5', ls=':', lw=1)
        axes[0, 0].legend()
        title = {'distance_m': 'DS13 · association subsets: independent 2 km position searches',
                 'gradient_strength': 'DS13 · score-gradient magnitude at the capture roof',
                 'gradient_strength_per_1000_windows': 'DS13 · local roof-gradient strength after adjusting for retained count'}[key]
        fig.suptitle(title, fontsize=18)
        fig.text(.5, .023, 'A and B independent. Fixed roof rankings; identical subsets in both RF arms. Three-start local searches, not a global certificate.\n'
            'Satellite rankings retain a fraction of satellites; GLRT ranking retains a fraction of assigned windows. Triangles = boundary; stars = search ambiguity.\n'
            '100% = assigned windows only; saved nonlinear receiver baseline fixed, extra RX lines / RF coefficient / timing refitted.', ha='center', fontsize=10)
        fig.tight_layout(rect=(0, .11, 1, .95)); fig.savefig(OUT / filename, dpi=160); plt.close(fig)
    sections = []
    for scan in 'AB':
        for method, name in NAMES.items():
            body = []
            for r in [r for r in rows if r['scan'] == scan and r['ranking'] == method]:
                status = 'Boundary' if r['boundary_limited'] else 'Interior'
                if r['minimum_neighbor_delta'] < -.001:
                    status += '; lower neighbor!'
                if r['ambiguity'] or r['polish_unconverged'] or r['lower_point_after_neighbors']:
                    status += '; search ambiguity'
                vals = [f"{100*r['fraction']:.0f}%", r['arm'], r['candidates'], r['windows'],
                    f"{r['distance_m']:.0f}", f"{r['east_m']:+.0f}, {r['north_m']:+.0f}",
                    f"{r['east_gradient_per_100m']:+.3f}, {r['north_gradient_per_100m']:+.3f}",
                    f"{r['gradient_strength']:.3f}", f"{r['gradient_strength_per_1000_windows']:.3f}",
                    f"{r['delta_score']:+.3f}", f"{r['successful_starts']}/3", status]
                body.append('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in vals) + '</tr>')
            headers = ['Top', 'RF arm', 'Satellites', 'Windows', 'Distance (m)', 'E, N (m)',
                'Roof gradient E, N /100m', 'Gradient magnitude', 'Magnitude /1,000 windows', 'Δ score vs roof', 'Converged starts', 'Search status']
            sections.append(f'<h2>Scan {scan} · {name}</h2><table><tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr>' + ''.join(body) + '</table>')
    doc = '<!doctype html><meta charset="utf-8"><title>DS13 subset position searches</title><style>body{font:15px system-ui;margin:30px;color:#18232c}table{border-collapse:collapse;font-variant-numeric:tabular-nums;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:right}th{background:#eef4f8}img{max-width:100%}p{max-width:1200px;line-height:1.5}</style><h1>DS13 · independent subset position searches</h1><p>Reference: capture-bound operator roof 37.849056280893684, −122.48575489722863; altitude modeled at WGS84 h=0. Not a surveyed truth claim. Fixed associations/rankings use the fitted-c roof result, shared with c=0; this is a conditional diagnostic, not held-out localization validation.</p><p>Lowest-RMS and most-support rankings retain ceil(fraction × satellites) and their assigned windows. Support = assigned-window count, span breaks ties. GLRT ranking retains ceil(fraction × assigned windows), ranked by refined margin (original fallback on failed refinement), with all original candidates retained. All 100% rows are the same result. Unassigned windows are excluded from every case, unlike the earlier all-top-window profile.</p><p>Score: same finite-set soft frequency likelihood plus Gaussian timing priors. Baseline nonlinear receiver correction fixed; RX constants/slopes, RF coefficient and timing are refitted. Sigma 200 Hz; common timing prior sigma 10 s, individual relative sigma 1 s; total timing constrained to ±20 s and common to ±10 s. c=0 and fitted-c use identical subsets, priors and search design. Candidate probability follows existing 0.8/N rule.</p><p>Search: roof, 12 seeded angular samples on 0.7/1.4/2 km rings, 8 cardinal/intercardinal boundary points; three separated local starts; best-site nuisance restart; 25 m neighbors and ±10 m roof-gradient check. Minimum means best found, not a certified global minimum. Boundary hits may prefer positions beyond the allowed disk. Positive roof gradient favors moving in the negative coordinate direction.</p><p>Raw scores are not comparable across different observation/candidate counts. Normalized gradients are descriptive, not uncertainty estimates. Ranking by roof-fit RMS uses the known position and can favor short tracks. Receiver/time/satellite balance changes with filtering; improvement is not proof that removed IDs were incorrect.</p><p><a href="summary.csv">All numerical results (CSV)</a></p><img src="minimum-distance.png"><img src="normalized-gradient.png">' + ''.join(sections)
    doc = doc.replace('<img src="normalized-gradient.png">', '<img src="roof-gradient.png"><img src="normalized-gradient.png">')
    doc = doc.replace('<p>Raw scores are not comparable',
        '<p>Cross-restart audit: restart the roof nuisance fit from the best off-roof vector, and vice versa. '
        'A lower nuisance branch triggers a bounded position follow-up; both RF arms use the same trigger. '
        'Initial searches have identical samples and 3 × 35-iteration budgets; follow-ups are adaptive. '
        'Near-stationary numerical stalls use alternative optimizers, always rechecked against the original 0.001 scaled-gradient tolerance. '
        'Stars flag competing starts, unfinished follow-up convergence, or a lower neighbor retained without a fresh local-minimum certificate. '
        'These cases are best-found solutions, not established minima. Lower-neighbor diagnostics refer to the previously checked center.</p>'
        '<p>Raw scores are not comparable')
    (OUT / 'report.html').write_text(doc)
    paths = [Path(__file__), HERE / 'subset_position_search.py', HERE / 'audit_subset_search.py',
             HERE / 'test_subset_position_search.py', HERE / 'orientation-evidence.json']
    for scan in 'AB':
        paths.append(OUT / f'{scan}-subsets.json')
    result_paths = sorted(OUT.glob('*-c.json'))
    receipt = dict(result_count=len(result_paths), table_rows=len(rows),
        maximum_gradient_fd_error=max(r['gradient_fd_error'] for r in rows),
        unique_boundary_cases=sorted({r['source'] for r in rows if r['boundary_limited']}),
        ambiguous_cases=sorted({r['source'] for r in rows if r['ambiguity'] or r['polish_unconverged'] or r['lower_point_after_neighbors']}),
        sources={str(p): digest(p) for p in paths + result_paths},
        scope='Independent scans. Same fixed subsets, candidate sets and model priors in RF arms. Shared initial search design/budget; adaptive numerical and nuisance-basin verification. Best found, not global certification.',
        scientific_checks='Every roof and retained best fit passes the unchanged 0.001 scaled nuisance-gradient criterion. Roof analytic gradients checked against +/-10m profiled differences. Lower-neighbor cases explicitly flagged; better neighbor retained.',
        original_run_failures_resolved_by='Saved A-glrt-50-zero-c and B-support-50-zero-c results pass the original convergence criterion after alternative-optimizer checks; initial run-status retains historical failure records.')
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print('ROWS', len(rows), 'worst FD error', max(r['gradient_fd_error'] for r in rows),
          'worst neighbor', min(r['minimum_neighbor_delta'] for r in rows))


if __name__ == '__main__':
    main()
