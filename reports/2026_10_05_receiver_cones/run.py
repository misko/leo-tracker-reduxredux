"""Fit and plot cones using all completed, frozen paired sky associations."""
import csv
import hashlib
import html
import json
from collections import defaultdict
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from cone_model import fit, probabilities, project, boundary

HERE = Path(__file__).resolve().parent
EXTENSION = HERE.parent/'2026_10_05_receiver_sky_82'
BASELINE = HERE.parent/'2026_10_04_t1_at_v1_replication'
sys.path.insert(0, str(EXTENSION))
sys.path.insert(0, str(BASELINE))
from receiver_sky_model import prepare, disk_grid, sky_xy
from sky_extension import temporal_kernel
from render_maps import ready_records
import render_receiver_sky as graphics

OUTCOME = ('RX0 only', 'RX1 only', 'Both receivers')
COLORS = ('#0072B2', '#D55E00')


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value))


def key(e):
    return e['scan'], e['satellite'], e['visit'], e['probe'], e['channel']


def write_csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def contours(ax, theta):
    for rx in (0, 1):
        edge = boundary(theta, rx)
        xy = sky_xy(edge)
        xy[edge[:, 2] < 0] = np.nan
        ax.plot(*xy.T, color='white', lw=3.2, zorder=8)
        ax.plot(*xy.T, color=COLORS[rx], lw=1.7, zorder=9,
                ls='-' if rx == 0 else '--')


def save(fig, filename, footer, top=.9, bottom=.13):
    fig.text(.5, .032, footer, ha='center', va='center', fontsize=10)
    fig.subplots_adjust(left=.03, right=.97, top=top, bottom=bottom, hspace=.2, wspace=.15)
    fig.savefig(HERE/filename, dpi=160)
    plt.close(fig)


def audit(events, data, result):
    p = probabilities(result['theta'], project(data['unit']))
    observed = p[np.arange(len(events)), data['outcome']]
    groups = defaultdict(list)
    tracks = defaultdict(list)
    outliers = []
    for i, e in enumerate(events):
        tracks[e['scan'], e['satellite']].append(i)
        if observed[i] < .05:
            groups[e['scan'], e['satellite'], int(e['time_s']//5), e['outcome']].append(i)
            outliers.append(dict(**e, observed_outcome_probability=float(observed[i]),
                                 predicted_rx0_only=float(p[i, 0]), predicted_rx1_only=float(p[i, 1]),
                                 predicted_both=float(p[i, 2]), weight=float(data['weight'][i])))
    grouped = []
    for (scan, satellite, block, outcome), inds in groups.items():
        u = data['unit'][inds].mean(axis=0); u /= np.linalg.norm(u)
        grouped.append(dict(scan=scan, satellite=satellite, time_block_s=block*5,
                            outcome=outcome, events=len(inds),
                            mean_probability=float(observed[inds].mean()),
                            east=float(u[0]), north=float(u[1]), up=float(u[2])))
    rows = []
    for (scan, sat), inds in tracks.items():
        mask = observed[inds] < .05
        w = data['weight'][inds]
        bad = np.array(inds)[mask]
        rows.append(dict(scan=scan, satellite=sat, paired_events=len(inds), outlier_events=int(mask.sum()),
            outlier_fraction=float(mask.mean()), weighted_outlier_fraction=float(w@mask/w.sum()),
            outlier_5s_blocks=len({int(events[i]['time_s']//5) for i in bad}),
            total_5s_blocks=len({int(events[i]['time_s']//5) for i in inds}),
            median_observed_probability=float(np.median(observed[inds])),
            rx0_only_outliers=sum(events[i]['outcome']==0 for i in bad),
            rx1_only_outliers=sum(events[i]['outcome']==1 for i in bad),
            both_outliers=sum(events[i]['outcome']==2 for i in bad)))
    rows.sort(key=lambda r: (-r['outlier_5s_blocks'], -r['outlier_events'], r['scan']))
    return p, observed, outliers, grouped, rows


def main():
    cohort = json.loads((EXTENSION/'cohort.json').read_text())
    original, added, pending = ready_records(cohort, allow_partial=True)
    records = original+added
    labels = [r['scan'] for r in records]
    assert len(labels) == len(set(labels))
    assert all(r['reconstruction_max_hz'] < 1e-5 for r in records)
    all_events = [e for r in records for e in r['events']]
    selected = lambda arm, gate: [e for e in all_events if e['arm']==arm and e['gate_hz']==gate]
    cases = {'full-fitted-c-600': selected('fitted-c', 600),
             'full-zero-c-600': selected('zero-c', 600),
             'full-fitted-c-300': selected('fitted-c', 300)}
    keyed = [{key(e): e for e in cases[name]} for name in ('full-fitted-c-600', 'full-zero-c-600')]
    shared = sorted(set(keyed[0]) & set(keyed[1]))
    for arm, bykey in zip(('fitted-c', 'zero-c'), keyed):
        cases[f'matched-{arm}-600'] = [bykey[k] for k in shared]
    for k in shared:
        np.testing.assert_allclose([keyed[0][k][c] for c in ('east', 'north', 'up', 'time_s')],
                                   [keyed[1][k][c] for c in ('east', 'north', 'up', 'time_s')],
                                   atol=1e-12, rtol=0)
    fitted = {}; datasets = {}
    for name, events in cases.items():
        assert len({key(e) for e in events}) == len(events)
        data = prepare(events)
        result = fit(data['unit'], data['outcome'], data['weight'])
        result.update(scans=data['scan_names'], case=name)
        fitted[name] = result; datasets[name] = data
        (HERE/f'{name}-fit.json').write_text(json.dumps(result, indent=2, allow_nan=False))
        print(name, len(events), result['parameters'], 'loss', result['in_sample_log_loss'],
              'outliers', result['raw_outliers_005'], 'converged', result['converged'], flush=True)
    np.testing.assert_allclose(datasets['matched-fitted-c-600']['weight'],
                               datasets['matched-zero-c-600']['weight'], atol=1e-12)
    main_name = 'full-fitted-c-600'
    result = fitted[main_name]; data = datasets[main_name]; events = cases[main_name]
    circular = fit(data['unit'], data['outcome'], data['weight'], circular=True, starts=4)
    (HERE/'circular-control-fit.json').write_text(json.dumps(circular, indent=2, allow_nan=False))
    p, observed, outliers, grouped, ranked = audit(events, data, result)
    write_csv(HERE/'outlier-events.csv', outliers)
    write_csv(HERE/'outlier-blocks.csv', grouped)
    write_csv(HERE/'satellite-outlier-summary.csv', ranked)
    x, y, inside, grid = disk_grid(81)
    epochs = {s['label']: s['capture_start_ns'] for s in cohort['scans']}
    empirical = temporal_kernel(events, grid, epochs, bootstrap=0)
    model = probabilities(result['theta'], project(grid))
    print('Kernel and outlier audit complete', len(grouped), 'marked groups', flush=True)
    np.savez_compressed(HERE/'sky-maps.npz', directions=grid, inside=inside,
                        empirical=empirical['probability'], model=model, supported=empirical['supported'],
                        event_probability=p, observed_probability=observed,
                        time_blocks=empirical['time_block_count'])
    xy_bad = sky_xy(np.array([[e['east'], e['north'], e['up']] for e in grouped])) if grouped else np.empty((0, 2))
    categories = np.array([e['outcome'] for e in grouped])
    fig, axs = plt.subplots(2, 3, figsize=(17, 11.5))
    for c in range(3):
        graphics.panel(axs[0, c], empirical['probability'][:, c], inside,
                       f'Observed · {OUTCOME[c]}', empirical['supported'])
        nbad = int(((observed < .05) & (data['outcome']==c)).sum())
        ntotal = int((data['outcome']==c).sum())
        graphics.panel(axs[1, c], model[:, c], inside,
                       f'Cone model · {OUTCOME[c]}\n{nbad:,} / {ntotal:,} outcomes below 5% probability',
                       empirical['supported'])
        for row in (0, 1):
            contours(axs[row, c], result['theta'])
        m = categories==c
        axs[1, c].scatter(xy_bad[m, 0], xy_bad[m, 1], marker='x', color='#C90034',
                          s=19, linewidths=.85, alpha=.72, zorder=11)
    par = result['parameters']
    fig.suptitle(f'{len(labels)} completed scans · identical elliptical cones, independent roll\n'
        f"Half-angles {par['major_half_angle_deg']:.1f}° × {par['minor_half_angle_deg']:.1f}° · "
        f"roll RX0 {par['rx0_roll_deg']:+.1f}°, RX1 {par['rx1_roll_deg']:+.1f}°", fontsize=18)
    handles = [Line2D([], [], color=COLORS[0], lw=2, label='RX0 cone edge'),
               Line2D([], [], color=COLORS[1], lw=2, ls='--', label='RX1 cone edge'),
               Line2D([], [], color='#C90034', marker='x', ls='', label='Low-probability observed outcome')]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .085), ncol=3, frameon=False)
    save(fig, 'cone-heatmaps-outliers.png',
        f'{len(events):,} satellite/channel/paired-20-ms outcomes; all used in fitting. A+B+N01–N17+N80; {len(pending)} additions pending.\n'
        'Heatmaps condition on ≥1 detection; empirical map uses 10° smoothing. Gray = insufficient support, not invisibility.\n'
        'One red × per scan/satellite/5-s/outcome group containing outliers. Nominal axes fixed; edges are latent 50% cone contours, not hard reception limits.',
        bottom=.15)
    # Show the model discrepancy rather than hiding it behind fitted contours.
    fig, axs = plt.subplots(1, 3, figsize=(17, 6.6))
    for c, ax in enumerate(axs):
        graphics.panel(ax, empirical['probability'][:, c]-model[:, c], inside,
                       f'Observed − cone model · {OUTCOME[c]}', empirical['supported'],
                       cmap='RdBu_r', vmin=-.5, vmax=.5)
        contours(ax, result['theta'])
    fig.suptitle('Where the shared-cone model misses the observed reception pattern', fontsize=18)
    save(fig, 'cone-model-discrepancy.png',
         'Positive = this outcome occurs more often than the model predicts. Common scale: probability difference.\n'
         'Empirical outcomes are smoothed; this is an in-sample descriptive mismatch, not held-out evidence or a localization score.')
    # Strict RF comparison uses identical opportunity keys, directions, weights,
    # parameter bounds, starts and optimizer budget. Only saved RF-arm outcomes differ.
    fig, axs = plt.subplots(2, 3, figsize=(17, 11))
    for row, arm in enumerate(('fitted-c', 'zero-c')):
        r = fitted[f'matched-{arm}-600']
        pred = probabilities(r['theta'], project(grid))
        for c in range(3):
            graphics.panel(axs[row, c], pred[:, c], inside, f'{arm} · {OUTCOME[c]}', empirical['supported'])
            contours(axs[row, c], r['theta'])
    fig.suptitle(f'Controlled RF sensitivity · {len(shared):,} identical paired opportunities', fontsize=18)
    save(fig, 'cone-rf-ablation.png',
         'Same refined inputs, selected satellite inventory, frozen timing, geometry, opportunity keys, weights and 12-start fitting budget.\n'
         'Saved calibration changes receiver-match outcomes. No new position fits; these maps do not measure position accuracy.')
    top = [r for r in ranked if r['outlier_events']][:18]
    fig, ax = plt.subplots(figsize=(12, 8))
    yy = np.arange(len(top))
    ax.barh(yy, [r['outlier_5s_blocks'] for r in top], color='#C90034', alpha=.8)
    ax.set_yticks(yy, [f"{r['scan']} · {r['satellite']}" for r in top])
    ax.invert_yaxis()
    for i, r in enumerate(top):
        ax.text(r['outlier_5s_blocks']+.4, i,
                f"{r['outlier_events']}/{r['paired_events']} events ({r['outlier_fraction']:.0%})", va='center', fontsize=9)
    ax.set_xlim(0, max([r['outlier_5s_blocks'] for r in top], default=1)*1.55+1)
    ax.set_xlabel('Distinct 5-second blocks containing an outcome with model probability < 5%')
    ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
    ax.set_title('Associations with the most persistent cone-model contradictions', fontsize=16)
    fig.text(.5, .035, 'Outliers are not automatically wrong satellite IDs. Geometry, sensitivity, polarization and association errors can all contribute.\n'
             'Counts are satellite/channel/paired-probe outcomes, not independent satellite passes.', ha='center', fontsize=10)
    fig.subplots_adjust(left=.18, right=.97, bottom=.15, top=.91)
    fig.savefig(HERE/'outlier-associations.png', dpi=160); plt.close(fig)
    summary = dict(completed_scans=labels, pending_additions=pending, target_scans=82,
        primary=result, circular_control=circular,
        cases={k: {a: b for a, b in r.items() if a!='runs'} for k, r in fitted.items()},
        marked_groups=len(grouped), tracks_with_outliers=sum(r['outlier_events']>0 for r in ranked),
        top_outlier_associations=top, common_rf_opportunities=len(shared),
        rf_outcome_changes=sum(keyed[0][k]['outcome']!=keyed[1][k]['outcome'] for k in shared),
        counts_are='Distinct satellite/channel/paired-probe outcomes, not unique GLRT windows or independent passes.',
        protocol=dict(geometry='Shared elliptical half-angles and margin softness; independent axial roll; no obstructions.',
            boresights='Nominal RX0 270/70 deg; RX1 90/70 deg. Fixed 40 deg separation, not surveyed RF axes.',
            roll='0 degrees: major axis toward increasing elevation; positive toward increasing azimuth. Modulo 180 degrees.',
            loss='Scan/encounter-balanced conditional categorical negative log likelihood, no added priors.',
            assumption='Conditional Bernoulli independence given direction; no scan/channel sensitivity fit.',
            weights='Same original scan and satellite/5-second balancing, no row compression or train/test split.',
            softening='logit_r = (z_r - hypot(x_r/tan(alpha), y_r/tan(beta))) / w; w dimensionless.',
            bounds='Half-angles [5,85] deg, softness [.01,2]; independent periodic roll.',
            outlier='Observed outcome probability below .05 under the fitted full-data model; descriptive, not significance.',
            selection='All refined passing alternatives checked for unique matches to frozen selected identities; exact aliases collapse.',
            support='At least 5 three-hour time blocks and 20 encounter blocks within 15 degrees; display mask only.',
            caveats='A is 10 MS/s; remaining 19 completed scans are 2.5 MS/s. Historical frequency folds retained. No position or identity refits.'),
        sources={str(BASELINE/'receiver-sky-maps/paired'/f'{r["scan"]}.json'):
                 hashlib.sha256((BASELINE/'receiver-sky-maps/paired'/f'{r["scan"]}.json').read_bytes()).hexdigest() for r in original},
        implementation={name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ['cone_model.py', 'run.py', 'test_cone_model.py']})
    for r in added:
        path = Path('/srv/bulk/leo/receiver-sky-82-20261005/paired')/f'{r["scan"]}.json'
        summary['sources'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    (HERE/'summary.json').write_text(json.dumps(summary, default=serial, indent=2, allow_nan=False))
    body = f'<h1>Shared elliptical receiver cones · {len(labels)} completed scans</h1>'
    body += '<p>Same shape and soft edge for RX0/RX1, separate rolls, fixed nominal pointing, no obstructions. All eligible full-data paired outcomes fitted. Existing Doppler associations are frozen; no localization improvement is claimed.</p>'
    body += f'<p>{len(events):,} primary paired outcomes; {len(outliers):,} have fitted observed-outcome probability below 5%. These are model outliers, not certified incorrect satellite associations. {len(pending)} requested scan additions remain pending.</p>'
    body += '<p>Detection alternatives are checked in both receivers; this is not limited to the historical top GLRT candidate. Each satellite contributes at most one receiver-pair outcome per probe. Absence of both receivers is unobserved; neither coverage nor absolute antenna gain is measured.</p>'
    for filename in ['cone-heatmaps-outliers.png', 'cone-model-discrepancy.png', 'outlier-associations.png', 'cone-rf-ablation.png']:
        body += f'<img src="{filename}" alt="{filename}">'
    body += '<h2>Parameters and protocol</h2><pre>'+html.escape(json.dumps(summary['protocol'], indent=2))+'</pre>'
    body += '<h2>Fitted cases</h2><pre>'+html.escape(json.dumps(summary['cases'], indent=2))+'</pre>'
    body += '<p>Model assumption: receiver detections are independent given sky direction before conditioning on at least one detection. Shared signal-strength variations can violate that assumption. Roll is unstable for nearly circular shapes. Unsupported regions are not evidence of blockage. All reported scores and outliers are in-sample.</p>'
    body += '<h2>Data</h2><ul>'+''.join(f'<li><a href="{name}">{name}</a></li>' for name in ['summary.json', 'outlier-events.csv', 'outlier-blocks.csv', 'satellite-outlier-summary.csv'])+'</ul>'
    (HERE/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Shared receiver cones</title><style>body{max-width:1500px;margin:30px auto;padding:20px;font:16px system-ui;line-height:1.5}img{width:100%}pre{white-space:pre-wrap}</style>'+body)
    print('COMPLETE', HERE, 'primary outliers', len(outliers), '/', len(events), flush=True)


if __name__ == '__main__':
    main()
