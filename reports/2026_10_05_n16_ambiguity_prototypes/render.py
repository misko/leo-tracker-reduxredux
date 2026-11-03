"""Reconstruct saved metrics and visualize the N16 ambiguity experiment."""
import csv
import html
import inspect
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
import numpy as np

import experiment as ex
from render_leave_one_satellite_out import check_stationarity

HERE = ex.HERE
SHORT = dict(baseline='Baseline', signal_only='Clutter\nfilter', drop_only='Drop\n+ soft',
    hard_only='Hard\nonly', drop_hard='Drop\n+ hard', penalty_1='Penalty\nη=1', penalty_2='Penalty\nη=2')
NAMES = {'fitted-c':'Fitted c', 'zero-c':'c = 0'}
COLORS = dict(baseline='#333333', drop_hard='#0072B2', penalty_1='#E69F00', penalty_2='#009E73')
MAIN = tuple(COLORS)


def collect():
    rows, audit = [], []
    for scan in ex.SCANS:
        data, receipt, saved, frozen, meta = ex.inputs(scan)
        for arm in ex.ARMS:
            for mode in ex.MODES:
                path = HERE/'results'/f'{scan}-{arm}-{mode}.json'
                # Preserve initial records; use a continuation if present.
                if (HERE/'polished'/path.name).exists():
                    path = HERE/'polished'/path.name
                r = json.loads(path.read_text())
                assert r['input_receipt'] == meta
                for dep, sha in r['dependencies'].items():
                    assert ex.digest(dep) == sha
                obj = ex.Objective(data, receipt['rf_center_hz'], arm, frozen, mode)
                m = ex.metrics(obj, data, frozen, r['best'], arm, receipt['rf_center_hz'])
                for key in m:
                    np.testing.assert_allclose(m[key], r['metrics'][key], atol=1e-7, rtol=0)
                np.testing.assert_allclose(m['objective'], r['best']['objective'], atol=1e-7, rtol=0)
                _, kkt = check_stationarity(obj, r['best'], radius_km=ex.RADIUS)
                np.testing.assert_allclose(kkt, r['best']['kkt_residual'], atol=1e-7, rtol=0)
                assert (kkt <= .001) == m['converged']
                assert np.linalg.norm(r['best']['point_km']) <= ex.RADIUS+1e-7
                assert not m['hard_invisible_windows']
                assert m['max_absolute_timing_s'] <= 20.+1e-7
                if arm == 'zero-c': assert r['best']['vector'][-1] == 0
                rows.append(dict(scan=scan, arm=arm, mode=mode, **m,
                    east_m=1000*r['best']['point_km'][0], north_m=1000*r['best']['point_km'][1],
                    source=str(path.relative_to(HERE)), source_sha256=ex.digest(path)))
                audit.append(dict(scan=scan, arm=arm, mode=mode,
                    reconstructed_objective_error=m['objective']-r['best']['objective'],
                    independently_recomputed_kkt=kkt,
                    mask_sha256=meta['mask_sha256'], input_sha256=meta['input_sha256']))
    lookup = {(r['scan'], r['arm'], r['mode']):r for r in rows}
    for r in rows:
        b = lookup[r['scan'], r['arm'], 'baseline']
        r['position_change_m'] = r['position_error_m']-b['position_error_m']
        r['full_rms_change_hz'] = r['full_fixed_winner_rms_hz']-b['full_fixed_winner_rms_hz']
        r['common_score_change'] = r['common_full_score']-b['common_full_score']
    with (HERE/'results.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    ex.save(HERE/'verification.json', audit)
    return rows, lookup


def aggregate(rows):
    summary = []
    for arm in ex.ARMS:
        for mode in ex.MODES:
            rs = [r for r in rows if r['arm'] == arm and r['mode'] == mode]
            e = np.array([r['position_error_m'] for r in rs])
            summary.append(dict(arm=arm, mode=mode, median_error_m=float(np.median(e)),
                mean_error_m=float(np.mean(e)), p90_error_m=float(np.quantile(e, .9)),
                improved=sum(r['position_change_m'] < -1 for r in rs),
                worsened=sum(r['position_change_m'] > 1 for r in rs),
                under_1km=int(np.sum(e < 1000)), converged=sum(r['converged'] for r in rs),
                boundary=sum(r['boundary'] for r in rs),
                median_full_rms_hz=float(np.median([r['full_fixed_winner_rms_hz'] for r in rs])),
                median_ambiguity_percent=float(np.median([r['full_ambiguous_percent'] for r in rs]))))
    ex.save(HERE/'summary.json', summary)
    return summary


def heatmap(lookup):
    modes = list(ex.MODES)[1:]
    fig, axes = plt.subplots(1, 2, figsize=(17, 10.5))
    limit = max(abs(lookup[s, a, m]['position_change_m']) for s in ex.SCANS for a in ex.ARMS for m in modes)
    limit = max(100., np.ceil(limit/250)*250)
    for ax, arm in zip(axes, ex.ARMS):
        values = np.array([[lookup[s, arm, m]['position_change_m'] for m in modes] for s in ex.SCANS])
        im = ax.imshow(values, cmap='PiYG_r', norm=TwoSlopeNorm(0, -limit, limit), aspect='auto')
        for i, s in enumerate(ex.SCANS):
            for j, m in enumerate(modes):
                r = lookup[s, arm, m]
                flag = ('△' if r['boundary'] else '')+('×' if not r['converged'] else '')
                ax.text(j, i, f'{int(np.rint(values[i,j])):+d}{flag}', ha='center', va='center',
                    color='white' if abs(values[i,j]) > .65*limit else 'black', fontsize=10)
        ax.set_xticks(range(len(modes)), [SHORT[m] for m in modes], fontsize=11)
        labels = []
        for s in ex.SCANS:
            baseline = lookup[s, arm, 'baseline']
            flags = ('△' if baseline['boundary'] else '')+('×' if not baseline['converged'] else '')
            labels.append(f'{s}  ({baseline["position_error_m"]:.0f} m{flags})')
        ax.set_yticks(range(16), labels, fontsize=10)
        ax.set_title(NAMES[arm], fontsize=16, pad=14)
        ax.set_ylabel('Scan (baseline position error)')
    cb = fig.colorbar(im, ax=axes, fraction=.023, pad=.025)
    cb.set_label('Change in position error (m) · negative / green = improvement')
    fig.suptitle('N01–N16 · does suppressing ambiguous associations improve position?', fontsize=19, y=.97)
    fig.text(.5, .035, 'Each cell = variant error − same-RF-arm baseline error. △ = boundary; × = unconverged (row labels flag the baseline).\n'
        'All variants use the same selected satellite bank; masks/identities frozen from each saved fitted-c fit. No cone weighting or new association search.\n'
        'In-sample development results, not held-out validation. Dropped windows are excluded from fitting, not reclassified as newly explained.', ha='center', fontsize=10)
    fig.subplots_adjust(left=.095, right=.86, top=.9, bottom=.14, wspace=.35)
    # Keep the colorbar outside the manually positioned panels.
    cb.ax.set_position([.90, .20, .018, .60])
    fig.savefig(HERE/'error-change.png', dpi=160); plt.close(fig)


def positions(lookup):
    fig, axes = plt.subplots(2, 1, figsize=(16, 9.5), sharex=True, sharey=True)
    for ax, arm in zip(axes, ex.ARMS):
        for mode in MAIN:
            rs = [lookup[s, arm, mode] for s in ex.SCANS]
            y = np.array([r['position_error_m'] for r in rs])
            ax.plot(range(16), y, '-o', color=COLORS[mode], label=ex.MODES[mode], lw=1.5, ms=5)
            for i, r in enumerate(rs):
                if r['boundary']: ax.scatter(i, y[i], marker='^', s=80, c=COLORS[mode], edgecolors='black', zorder=5)
                if not r['converged']: ax.scatter(i, y[i], marker='x', s=45, c='black', zorder=6)
        ax.axhline(4000, color='.5', ls=':'); ax.set_ylim(0, 4250)
        ax.set_title(NAMES[arm], fontsize=15); ax.set_ylabel('Distance from known roof (m)')
        ax.grid(alpha=.2); ax.set_axisbelow(True)
    axes[0].legend(ncol=4, frameon=True, facecolor='white', framealpha=1., loc='upper center', fontsize=10)
    axes[1].set_xticks(range(16), ex.SCANS)
    fig.suptitle('N01–N16 · absolute position error of the two ambiguity prototypes', fontsize=19)
    fig.text(.5, .035, 'Drop + hard: discard second-satellite responsibility >5% and clutter-dominated windows, then fit fixed winners.\n'
        'Penalty: keep all original windows; add conditional identity min-entropy with η=1 or 2. Same priors and maximum budgets.\n'
        'Triangles = 4 km boundary, not unconstrained minima. × = unconverged. Lower frequency error alone does not establish better localization.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .12, 1, .96)); fig.savefig(HERE/'position-error.png', dpi=160); plt.close(fig)


def cohort(summary):
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    for j, arm in enumerate(ex.ARMS):
        rs = [r for r in summary if r['arm'] == arm]
        x = np.arange(7)+(j-.5)*.36
        for ax, metric in zip(axes, ['median_error_m', 'mean_error_m']):
            y = [r[metric] for r in rs]
            ax.bar(x, y, width=.34, label=NAMES[arm], color=['#0072B2','#D55E00'][j])
            for xx, yy in zip(x, y): ax.text(xx, yy+30, f'{yy:.0f}', ha='center', fontsize=9)
    for ax, name in zip(axes, ['Median', 'Mean']):
        ax.set_title(f'{name} position error over 16 scans', fontsize=14)
        ax.set_ylabel('Distance from known roof (m)'); ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
        ax.set_xticks(range(7), list(SHORT.values()), fontsize=10); ax.set_ylim(bottom=0)
    axes[0].legend(frameon=False)
    fig.suptitle('N01–N16 · cohort summary, including controls', fontsize=19)
    fig.text(.5, .035, 'Same observations and candidate sets before filtering; fitted-c and c=0 use identical frozen masks and starts.\n'
        'All best-found results included, including boundary and unconverged cases flagged in the per-scan charts. No per-scan cherry-picking.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .13, 1, .94)); fig.savefig(HERE/'cohort-summary.png', dpi=160); plt.close(fig)


def diagnostics(lookup):
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    for i, arm in enumerate(ex.ARMS):
        for ax, metric, ylabel in zip(axes[i], ['full_fixed_winner_rms_hz','full_ambiguous_percent'],
                ['Same original windows / frozen-winner RMS (Hz)', 'Original windows with second satellite >5% (%)']):
            for mode in MAIN:
                ax.plot(range(16), [lookup[s,arm,mode][metric] for s in ex.SCANS], '-o',
                    color=COLORS[mode], label=ex.MODES[mode], ms=4)
            ax.set_title(NAMES[arm]); ax.set_xticks(range(16), ex.SCANS, rotation=45)
            ax.set_ylabel(ylabel); ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=9, frameon=False)
    fig.suptitle('Frequency fit and responsibility ambiguity are separate from position accuracy', fontsize=17)
    fig.text(.5,.025, 'Every diagnostic uses ALL original fitted windows, including rows removed from the hard/drop fits.\n'
        'Same frozen labels for RMS; unpenalized soft model for responsibility reporting. Lower ambiguity is not proof of correct satellite identity.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0,.095,1,.95)); fig.savefig(HERE/'diagnostics.png', dpi=150); plt.close(fig)


def retention():
    rs = [json.loads((HERE/'inputs'/f'{s}.json').read_text()) for s in ex.SCANS]
    total = np.array([r['original_windows'] for r in rs])
    keep = np.array([r['retained'] for r in rs])
    ambiguous = np.array([r['ambiguous_dropped'] for r in rs])
    extra = np.array([r['extra_clutter_dropped'] for r in rs])
    assert np.array_equal(keep+ambiguous+extra, total)
    fig, ax = plt.subplots(figsize=(14, 5.5))
    x = np.arange(16)
    ax.bar(x, keep/total*100, color='#0072B2', label='Retained for drop + hard / soft')
    ax.bar(x, ambiguous/total*100, bottom=keep/total*100, color='#E69F00', label='Second satellite >5%')
    ax.bar(x, extra/total*100, bottom=(keep+ambiguous)/total*100, color='#888888', label='Additional clutter-dominated')
    for i, (k, t) in enumerate(zip(keep, total)):
        ax.text(i, 43, f'{k:,}\n/ {t:,}', ha='center', color='white', fontsize=9)
    ax.set_xticks(x, ex.SCANS); ax.set_ylabel('Share of original assigned windows (%)')
    ax.set_ylim(0, 101); ax.legend(ncol=3, frameon=False, loc='lower center', bbox_to_anchor=(.5,1.02))
    fig.suptitle('What the frozen ambiguity filter removes', fontsize=18)
    fig.text(.5,.03,'Same frozen masks in fitted-c and c=0. These are retained fitting windows, not a recalculated association-coverage percentage.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.08,1,.93)); fig.savefig(HERE/'window-retention.png',dpi=160); plt.close(fig)


def report(rows, lookup, summary):
    body = '<!doctype html><meta charset="utf-8"><title>N16 ambiguity prototypes</title><style>body{font:16px system-ui;max-width:1450px;margin:35px auto;padding:0 24px;line-height:1.55}img{width:100%}table{border-collapse:collapse}th,td{padding:7px;border-bottom:1px solid #ddd;text-align:right}th:first-child,td:first-child{text-align:left}</style>'
    body += '<h1>N01–N16: ambiguity prototypes</h1><p>Independent full-data position fits; matched fitted-c and c=0; 4 km bounded local searches. No new GLRT, greedy/replacement, orbit bank, cone prior, folds or RF collection.</p>'
    body += '<p>Two-pass development diagnostic: responsibilities and fixed identities are frozen from each saved fitted-c position fit, shared by both RF arms. The original windows were already selected/assigned by top-one T1-AT. Upstream calibration used the known roof. These are not held-out or blind validation results, and “retained windows” is not a new association-coverage metric.</p>'
    body += '<h2>What this experiment found</h2><p>Neither requested prototype improves the cohort median or mean position error in either RF arm. Keep the soft baseline as the reference; these results do not support a universal ambiguity cut or uniqueness penalty.</p><ul>'
    for arm in ex.ARMS:
        stats = {r['mode']:r for r in summary if r['arm'] == arm}
        body += f'<li>{NAMES[arm]} median error: baseline {stats["baseline"]["median_error_m"]:.0f} m; drop + hard {stats["drop_hard"]["median_error_m"]:.0f} m; penalty η=1 {stats["penalty_1"]["median_error_m"]:.0f} m; penalty η=2 {stats["penalty_2"]["median_error_m"]:.0f} m.</li>'
    body += '</ul><p>There are real scan-specific improvements, not a blanket failure: fitted-c N04 improves from 1,003 to 747 m with η=1, while N12 worsens from 2,718 to 2,955 m. Drop+hard improves fitted-c N14 by 181 m but worsens N03 by 257 m. Uniqueness within a restricted selected satellite bank does not establish correct identity.</p>'
    body += '<p>The drop+hard filter retains 37,727 of 42,610 original assigned windows (88.5%): 4,123 are removed for second-satellite responsibility &gt;5%, plus 760 additional clutter-dominated windows. The controls help distinguish loss of observations from the effect of forcing a fixed identity.</p>'
    body += '<h2>Protocol</h2><p>Unchanged N-cohort control: wrapped Gaussian σ=200 Hz; q=0.8/K times the compact 0–1° horizon ramp; clutter rate 2; common timing prior σ=10 s, relative timing σ=1/3 s; common timing bound ±10 s, total satellite shifts ±20 s. Extra RX offsets/slopes and c are refitted. The c=0 arm disables c only in the final fit; both arms share the upstream fitted-c receiver calibration.</p>'
    body += '<p>Clutter filter removes windows whose top satellite does not beat clutter. Drop+soft also removes second-satellite responsibility &gt;5%. Hard-only keeps the clutter filter but fixes IDs; drop+hard applies both filters and a pure fixed-winner Gaussian (no switching or clutter fallback). No weight renormalization; satellite bank and timing priors remain unchanged even for IDs with no retained hard-labeled windows.</p>'
    body += '<p>Penalty variants add η Σ<sub>g</sub>[−log max<sub>s</sub> π<sub>gs</sub>], η=1,2, with π conditional on signal, dynamically recomputed at each trial position/timing. This favors a single explanation but can artificially separate competing predictions; it is not extra physical evidence. The max creates derivative kinks at exact ties.</p>'
    body += '<p>Three identical starts (saved fitted-c best, c=0 best, fitted-c roof), 4 s each; 8 s Fisher polish; if unconverged up to 12 s SLSQP and 12 s Fisher. Stop early at constrained scaled KKT≤0.001. Select by actual objective only, never position error. Boundary solutions are not unconstrained minima.</p>'
    if (HERE/'polish-protocol.json').exists():
        body += '<p>All cases additionally offered the same bounded continuation policy, stopping early on convergence; see <a href="polish-protocol.json">continuation receipt</a>.</p>'
    body += '<h2>Cohort results</h2><img src="cohort-summary.png"><table><tr><th>RF arm</th><th>Mode</th><th>Median m</th><th>Mean m</th><th>Improved /16</th><th>&lt;1 km</th><th>Converged /16</th><th>Boundary</th><th>Median full RMS Hz</th></tr>'
    for r in summary:
        body += '<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [NAMES[r['arm']],ex.MODES[r['mode']],round(r['median_error_m']),round(r['mean_error_m']),r['improved'],r['under_1km'],r['converged'],r['boundary'],round(r['median_full_rms_hz'],1)])+'</tr>'
    body += '</table><p>“Improved” uses more than 1 m reduction versus the renewed same-arm baseline, not versus a weaker RF arm. Mean and median can disagree; inspect per-scan outcomes. Raw objective values across models/subsets are not comparable.</p>'
    body += '<h2>Per-scan comparisons</h2><img src="error-change.png"><img src="position-error.png"><h2>Frequency and ambiguity diagnostics</h2><img src="diagnostics.png">'
    body += '<h2>Retained windows</h2><img src="window-retention.png"><table><tr><th>Scan</th><th>Original assigned</th><th>Second &gt;5%</th><th>Extra clutter</th><th>Drop+hard retained</th></tr>'
    for s in ex.SCANS:
        r = json.loads((HERE/'inputs'/f'{s}.json').read_text())
        body += '<tr>'+''.join(f'<td>{v}</td>' for v in [s,r['original_windows'],r['ambiguous_dropped'],r['extra_clutter_dropped'],r['retained']])+'</tr>'
    body += '</table><h2>Verification and files</h2>'
    body += f'<p>{sum(r["converged"] for r in rows)}/{len(rows)} fits meet KKT≤0.001; {sum(r["boundary"] for r in rows)} reach the 4 km boundary. All saved objective values and diagnostic metrics reconstruct. No admitted hard-assignment solution has a below-horizon fixed owner. The implementation passes synthetic frequency/visibility derivative checks and cached N01 full-model gradient and control-parity tests.</p>'
    unfinished = [r for r in rows if not r['converged']]
    body += '<p>Uncertified cases: '+', '.join(f'{r["scan"]} / {NAMES[r["arm"]]} / {ex.MODES[r["mode"]]} (KKT {r["kkt"]:.4g})' for r in unfinished)+'. They remain in summary statistics and are marked × in the charts; do not treat them as certified minima.</p>'
    body += '<p><a href="results.csv">All 224 results CSV</a> · <a href="summary.json">Cohort summary</a> · <a href="protocol.json">Protocol</a> · <a href="verification.json">Reconstruction audit</a> · <a href="experiment.py">Runner</a> · <a href="likelihood.py">Likelihood</a></p>'
    (HERE/'report.html').write_text(body)


if __name__ == '__main__':
    rows, lookup = collect()
    summary = aggregate(rows)
    heatmap(lookup); positions(lookup); cohort(summary); diagnostics(lookup); retention(); report(rows, lookup, summary)
    print(json.dumps(summary, indent=2))
    print('Reconstructed',len(rows),'fits; converged',sum(r['converged'] for r in rows))
