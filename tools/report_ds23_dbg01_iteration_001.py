"""Publishable figures/tables for one bounded, current-method DBG01 iteration.

GPS is report-only. RF choices and paired inference are sealed and independently
audited before this tool evaluates accuracy. This does not promote an ALGO ID.
"""

import csv
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.text import Text
import numpy as np

import run_dbg01_latest_worst as study
import report_dbg01_algo02_ds23_0268 as dbg_figures
from audit_ds23_algo01_coverage import retained_metrics
from dbg01_unassociated import ownership
from evaluate_ds23_phase_refreshed import extend_associations
from plot_ds23_worst_association_bottleneck import raw_track_values
from probe_ds23_single_curved_reentry import OUT as REENTRY
from probe_ds23_support_aware_reentry import OUT as SUPPORT
from probe_ds23_worst_association_bottleneck import OUT as RAW, inventory, build, setup
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_001'


def csv_write(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def polynomial_segments(track, indices, by_id):
    indices = np.asarray(indices, int)
    times, native = raw_track_values(track, indices, by_id)
    canonical = np.asarray(track['values'])[indices]
    result = []
    for piece in track['pieces']:
        selected = np.flatnonzero((times >= piece['start_s']-1e-8)&(times <= piece['end_s']+1e-8))
        if len(selected) < 2:
            continue
        shifts = native[selected]-canonical[selected]
        if np.ptp(shifts) > 1e-5:
            # An observed alias change is a display break, never extra evidence.
            cuts = np.flatnonzero(abs(np.diff(shifts)) > 1e-5)+1
        else:
            cuts = []
        for part in np.split(selected, cuts):
            cuts2 = np.flatnonzero((np.diff(indices[part]) > 1)|(np.diff(times[part]) > 10.))+1
            for run in np.split(part, cuts2):
                if len(run) < 2:
                    continue
                grid = np.linspace(times[run].min(), times[run].max(), 100)
                value = np.polynomial.legendre.legval((grid-piece['reference_time_s'])/piece['time_scale_s'],
                                                     piece['coefficients_hz'])
                result.append((grid, value+float(np.median(native[run]-canonical[run]))))
    return result


def glrt_figure(d, inv, prefix, associated):
    by_id = {o['observation_id']: o for o in d['observations']}
    owned = set(inv['accepted_observation_ids'])
    labels = {}
    for row in inv['associations']['tracks']:
        if not row['compatible']:
            continue
        track = next(t for t in d['scan'].tracks if t['key'] == row['component'])
        for oid in row.get('observation_ids', track['observation_ids']):
            labels[oid] = row['norad']
    families = sorted(set(labels.values()))
    channels = sorted({o['channel'] for o in d['observations']})
    palette = plt.get_cmap('tab20')
    colors = {n: palette(k % 20) for k, n in enumerate(families)}
    fig, axes = plt.subplots(2, len(channels), figsize=(4*len(channels), 7), squeeze=False)
    for rx in [1, 2]:
        for col, channel in enumerate(channels):
            ax = axes[rx-1, col]
            observations = [o for o in d['observations'] if (o['receiver'], o['channel']) == (rx, channel)]
            ax.scatter([o['time_s'] for o in observations], [o['measured_cfo_hz']/1000 for o in observations],
                       c='0.85', s=8)
            if associated:
                for n in families:
                    rows = [o for o in observations if labels.get(o['observation_id']) == n]
                    ax.scatter([o['time_s'] for o in rows], [o['measured_cfo_hz']/1000 for o in rows],
                               color=colors[n], s=10)
            else:
                rows = [o for o in observations if o['observation_id'] not in owned]
                ax.scatter([o['time_s'] for o in rows], [o['measured_cfo_hz']/1000 for o in rows], c='crimson', s=10)
            for k, track in enumerate(d['scan'].tracks):
                if (track['receiver'], track['channel']) != (rx, channel):
                    continue
                indices = [i for i, oid in enumerate(track['observation_ids']) if (oid in owned) == associated]
                if associated:
                    groups = [(n, [i for i in indices if labels.get(track['observation_ids'][i]) == n]) for n in families]
                else:
                    groups = [(None, indices)]
                for n, subset in groups:
                    for times, values in polynomial_segments(track, subset, by_id):
                        ax.plot(times, values/1000, color=colors[n] if associated else palette(k % 20), lw=1.2)
            ax.set(title=f'RX{rx} CH{channel}', xlabel='Device time (s)', ylabel='Raw GLRT CFO (kHz)')
            ax.grid(alpha=.2)
    kind = 'associated by satellite hypothesis' if associated else 'unassociated points and graph polynomials'
    fig.suptitle(f"{d['scan'].case} · {prefix} · fitted c · {inv['associated']}/{inv['total_GLRT']} ({inv['percent']:.2f}%)\n"
                 f'{kind}; gray = all original GLRT; polynomial samples are display only')
    fig.tight_layout()
    target = OUT/'figures'/f"{d['scan'].case}_{prefix}_{'associated' if associated else 'unassociated'}_GLRT.png"
    fig.savefig(target, dpi=150)
    plt.close(fig)


def current_dbg_figures(case):
    out = study.configure(case)
    dbg_figures.CASE, dbg_figures.OUT = case, out
    dbg_figures.context = study.engine.context
    audit = read(out/'audit.json')
    # Reuse the established plotting implementation, naming the actual method.
    original_save = Figure.savefig
    def labeled_save(fig, *args, **kwargs):
        for item in fig.findobj(Text):
            item.set_text(item.get_text().replace('ALGO02', 'ALGO02/03 research'))
        return original_save(fig, *args, **kwargs)
    Figure.savefig = labeled_save
    try:
        dbg_figures.surfaces(audit)
        dbg_figures.restarts(audit)
        interventions = dbg_figures.influence(audit)
    finally:
        Figure.savefig = original_save
    for name in ['loss_gradient_10km.png', 'convergence_10km.png', 'influence_and_controls.png', 'loss_decomposition.png']:
        shutil.copyfile(out/name, OUT/'figures'/(case+'_'+name))
    return interventions


def family_rows(case, d):
    root = RAW/case/'DBG01'
    result = []
    for path in sorted(root.glob('family_[0-9][0-9].json')):
        original = read(path)
        mask = d['keep'].copy()
        for row, sl in zip(d['base'].rows, d['base'].slices, strict=True):
            if row['candidate_norad'] == original['target']:
                mask[sl] = False
        entries = [e for e in d['entries'] if e['norad'] != original['target']]
        dd = dict(d, keep=mask, entries=entries)
        for arm, saved in original['arms'].items():
            p = build(dd, arm, saved['phase_reference'])
            x = np.asarray(saved['endpoint_east_north_km'])
            delta = p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta) > 1e-5:
                raise ValueError('family ablation objective did not replay')
            extended = extend_associations(p, x, retained_metrics(p, x))
            lookup = {t['key']: t for t in d['scan'].tracks}
            accepted = ownership([dict(r, observation_ids=r.get('observation_ids', lookup[r['component']]['observation_ids']))
                                  for r in extended['tracks'] if r['norad'] != original['target']])
            result.append(dict(case=case, excluded_norad=original['target'], arm=arm,
                error_km=position_error(saved['endpoint_latlon']), frequency_RMS_hz=saved['RMS_hz'],
                associated_points=len(accepted), all_GLRT=len(d['observations']),
                associated_percent=100*len(accepted)/len(d['observations']),
                removed_curved_points=original['deleted_curved_points'],
                removed_predictive_points=original['deleted_predictive_points'],
                paired_gates_valid=original['paired_gates_valid'], final_phase_change_s=saved['final_phase_change_s'],
                endpoint_replay_difference=delta, diagnostic_only_no_GPS_selected_deletion=True))
    return result


def overview(rows, ceilings):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
    cases = list(ceilings)
    for k, case in enumerate(cases):
        eligible = [r for r in rows if r['case'] == case and r['arm'] == 'fitted_c']
        subset = [eligible[0], max(eligible[1:], key=lambda r:r['curved_position_points'])]
        for j, row in enumerate(subset):
            x = k+(j-.5)*.25
            axes[0].bar(x, row['associated_percent'], width=.23, color=['tab:blue', 'tab:orange'][j],
                        label=['Published incumbent', 'Selected passing prototype'][j] if k == 0 else None)
            axes[0].text(x, row['associated_percent']+1, f"{row['associated_percent']:.1f}%", ha='center', fontsize=8)
            axes[1].bar(x, row['position_error_km'], width=.23, color=['tab:blue', 'tab:orange'][j])
            axes[1].text(x, row['position_error_km']+.2, f"{row['position_error_km']:.2f}", ha='center', fontsize=8)
        c = ceilings[case]
        axes[2].bar(k, c['graph_owned_percent'], color='tab:green')
        axes[2].text(k, c['graph_owned_percent']+1, f"{c['graph_owned_percent']:.1f}%", ha='center')
    axes[0].axhline(90, color='crimson', ls='--', label='90% aspiration')
    axes[2].axhline(90, color='crimson', ls='--')
    axes[1].axhline(.5, color='seagreen', ls='--')
    for ax in axes:
        ax.set_xticks(range(len(cases)), cases)
        ax.grid(axis='y', alpha=.2)
    axes[0].set(ylabel='Associated original GLRT (%)', ylim=(0, 100))
    axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Position error (km)')
    axes[2].set(ylabel='Maximum coverage using current graph (%)', ylim=(0, 100))
    fig.suptitle('Iteration 001 · conditional passing-fit prototype, not a new ALGO version\n'
                 '0326 new identity remains ambiguous at nomination; no forced 90% association')
    fig.savefig(OUT/'figures/iteration_summary.png', dpi=165)
    plt.close(fig)


def nomination_and_graph_figures(cases):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout='constrained')
    case = 'DS23-0326'
    row = read(REENTRY/(case+'_nominations.json'))['targets'][0]
    all_numbers = sorted({r['norad'] for name in ['fixed', 'full'] for r in row['coarse_rankings'][name][:5]})
    for offset, name, color in [(-.12, 'fixed', 'tab:red'), (.12, 'full', 'tab:blue')]:
        ranks = {r['norad']: k+1 for k, r in enumerate(row['coarse_rankings'][name])}
        values = [ranks.get(n, 9) for n in all_numbers]
        axes[0].scatter(values, np.arange(len(values))+offset, color=color,
                        label='Fixed receiver mean' if name == 'fixed' else 'Shared receiver uncertainty')
    axes[0].set_yticks(range(len(all_numbers)), all_numbers)
    axes[0].set_xticks(range(1, 10), [str(k) for k in range(1, 9)]+['>8'])
    axes[0].set(xlabel='Candidate rank in full causal catalogue', title='0326: missing RX2 calibration changes nomination')
    axes[0].invert_yaxis()
    axes[0].legend(fontsize=8)
    medians = []
    for c in cases:
        medians.extend((c, r['target']['component'].split('-RF')[0].replace(c+'-', ''),
                        r['radio_prediction_SD_hz_quantiles'][1]) for r in read(REENTRY/(c+'_nominations.json'))['targets'])
    axes[1].barh([c.replace('DS23-', '')+' '+t for c, t, _ in medians], [s for _, _, s in medians], color='tab:blue')
    axes[1].set(xlabel='Median shared calibration prediction SD (Hz)', xscale='log', title='Prediction uncertainty is correlated across the curve')
    axes[1].grid(axis='x', alpha=.2)
    fig.savefig(OUT/'figures/receiver_uncertainty_nominations.png', dpi=165)
    plt.close(fig)
    d = setup(case)
    track = d['scan'].tracks[row['target']['track_index']]
    times = np.asarray(track['times'])
    piece = track['pieces'][0]
    polynomial = np.polynomial.legendre.legval((times-piece['reference_time_s'])/piece['time_scale_s'], piece['coefficients_hz'])
    residual = np.asarray(track['values'])-polynomial
    by_id = {o['observation_id']: o for o in d['observations']}
    _, native = raw_track_values(track, np.arange(len(times)), by_id)
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), layout='constrained', sharex=True)
    axes[0].scatter(times, native/1000, s=22, c='black', label='Original GLRT')
    axes[0].plot(times, (native-residual)/1000, label='Persisted cubic graph polynomial')
    axes[0].set(ylabel='Raw CFO (kHz)')
    axes[1].plot(times, residual, '.-', color='tab:green', label=f'Polynomial RMS {np.sqrt(np.mean(residual**2)):.1f} Hz')
    axes[1].set(ylabel='Polynomial residual (Hz)')
    for n, color in [(59699, 'tab:blue'), (50832, 'tab:orange')]:
        candidate = next(r for r in row['candidates'] if r['norad'] == n)
        axes[2].plot(times, candidate['residual_hz'], '.-', color=color,
                     label=f"{n}: conditional RMS {candidate['conditional_RMS_hz']:.1f} Hz")
    axes[2].set(xlabel='Time in scan (s)', ylabel='Candidate posterior residual (Hz)')
    for ax in axes:
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    for ax in axes[1:]:
        ax.axhline(0, c='black', lw=.6)
    fig.suptitle('DS23-0326 RX2 CH4 · 21 points · one cubic piece\n'
                 'Candidate curves integrate receiver uncertainty; these are conditional hypotheses, not satellite truth')
    fig.savefig(OUT/'figures/DS23-0326_graph_vs_satellite_residuals.png', dpi=165)
    plt.close(fig)


def residual_figures(case, d, fits, support):
    series = [('Published incumbent', fits['baseline_arms'])]
    if fits['selected']:
        series.append(('Single-curve prototype', fits['policy_arms']))
    if support and support['selected']:
        series.append(('Support-aware growth', support['selected']['arms']))
    lookup = {t['key']: t for t in d['scan'].tracks}
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout='constrained')
    for col, arm in enumerate(['c0', 'fitted_c']):
        for name, pair in series:
            for gate in pair[arm]['gates']['tracks']:
                residual = gate['conditional_residual_gate']
                rows.append(dict(case=case, method=name, arm=arm, component=gate['component'],
                    norad=gate['norad'], points=gate['points'], compatible=gate['compatible'],
                    rms_hz=residual['rms_hz'], mean_hz=residual['mean_hz'], **residual['diagnostics']))
            selected = rows[-len(pair[arm]['gates']['tracks']):]
            durations = [lookup[r['component']]['end_s']-lookup[r['component']]['start_s'] for r in selected]
            axes[0, col].scatter(durations, [r['rms_hz'] for r in selected],
                s=[max(15, r['points']) for r in selected], alpha=.6, label=name)
            axes[1, col].scatter([r['slope_z'] for r in selected],
                [r['quadratic_bic_gain'] for r in selected], alpha=.6, label=name)
        axes[0, col].axhline(450, color='gray', ls='--', label='450 Hz RMS gate')
        axes[0, col].set(title=arm, xlabel='Track span (s)', ylabel='Conditional RMS (Hz)')
        axes[1, col].axhline(10, color='gray', ls='--')
        axes[1, col].axvline(3, color='gray', ls='--')
        axes[1, col].set(xlabel='Absolute residual slope z', ylabel='Quadratic BIC gain')
    for ax in axes.flat:
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    fig.suptitle(f'{case} · retained curved-track residual checks\n'
                 'All original points remain; additional residual, alias, elevation and support gates also apply')
    fig.savefig(OUT/'figures'/(case+'_track_residuals.png'), dpi=165)
    plt.close(fig)
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    for name in ['figures', 'tables', 'evidence', 'source/tools', 'source/tests']:
        (OUT/name).mkdir(parents=True, exist_ok=True)
    independent = read(RAW/'independent_iteration_audit.json')
    assert independent['all_passed']
    assert read(RAW/'RF_restart_selection.json')['selection_frozen_before_new_geographic_error_comparison']
    cases = read(RAW/'protocol.json')['cases']
    rows, families, ceilings, failures, diagnoses, controls, residuals = [], [], {}, [], {}, [], []
    for case in cases:
        d = setup(case)
        baseline = read(RAW/case/'inventory.json')['arms']
        fits = read(REENTRY/(case+'_positions.json'))
        checked = read(REENTRY/(case+'_audit.json'))
        assert checked['all_passed']
        new = checked['coverage']
        inv = baseline['fitted_c']
        ceilings[case] = dict(all_GLRT=inv['total_GLRT'], graph_owned=inv['total_GLRT']-inv['outside_graph_points'],
                              graph_owned_percent=100*(1-inv['outside_graph_points']/inv['total_GLRT']),
                              outside_graph=inv['outside_graph_points'],
                              extra_graph_points_required_for90_percent=max(0, int(np.ceil(.9*inv['total_GLRT']))
                                                                           -(inv['total_GLRT']-inv['outside_graph_points'])))
        for method, arms, coverage in [('Published incumbent', fits['baseline_arms'], baseline),
                                       ('Single-curve prototype', fits['policy_arms'], new)]:
            for arm, r in arms.items():
                rows.append(dict(case=case, method=method, arm=arm,
                    position_error_km=position_error(r['endpoint_latlon']),
                    associated_points=coverage[arm]['associated'], all_GLRT=coverage[arm]['total_GLRT'],
                    associated_percent=coverage[arm]['percent'], RMS_hz=r['RMS_hz'],
                    curved_position_points=r['active_points'], predictive_points=coverage[arm]['predictive_points'],
                    endpoint_latitude=r['endpoint_latlon'][0], endpoint_longitude=r['endpoint_latlon'][1],
                    selected_by_GPS=False))
        support_path = SUPPORT/(case+'_audited.json')
        support = None
        if support_path.exists():
            support = read(support_path)
            assert support['all_passed']
            selected_support = support['selected']
            if selected_support:
                for arm, r in selected_support['arms'].items():
                    cov = support['coverage'][arm]
                    rows.append(dict(case=case, method='Support-aware growth', arm=arm,
                        position_error_km=position_error(r['endpoint_latlon']),
                        associated_points=cov['associated'], all_GLRT=cov['total_GLRT'],
                        associated_percent=cov['percent'], RMS_hz=r['RMS_hz'],
                        curved_position_points=r['active_points'], predictive_points=cov['predictive_points'],
                        endpoint_latitude=r['endpoint_latlon'][0], endpoint_longitude=r['endpoint_latlon'][1],
                        selected_by_GPS=False))
                for associated in [True, False]:
                    glrt_figure(d, support['coverage']['fitted_c'], 'support_aware', associated)
        residuals.extend(residual_figures(case, d, fits, support))
        for associated in [True, False]:
            glrt_figure(d, baseline['fitted_c'], 'published', associated)
            selected = fits['selected']
            dd = dict(d, node=selected['node'], keep=np.asarray(selected['mask'], bool),
                      entries=selected['entries'], means=np.asarray(selected['means'])) if selected else d
            glrt_figure(dd, new['fitted_c'], 'prototype', associated)
        for trial in fits['trials']:
            for arm, r in trial['arms'].items():
                dd = dict(d, node=trial['node'], keep=np.asarray(trial['mask'], bool),
                          entries=trial['entries'], means=np.asarray(trial['means']))
                probe = build(dd, arm, r['phase_reference'])
                state = probe.state(np.asarray(r['endpoint_east_north_km']))
                _, elevation = probe.conditional_frequency(np.asarray(r['endpoint_east_north_km']))
                owners = {}
                for gate in r['gates']['tracks']:
                    if gate['conditional_residual_gate']['compatible']:
                        track = next(t for t in d['scan'].tracks if t['key'] == gate['component'])
                        owners.setdefault(gate['candidate_index'], set()).add((track['receiver'], track['channel']))
                failed = []
                for gate in r['gates']['tracks']:
                    if gate['compatible']:
                        continue
                    slot = next(k for k, row in enumerate(probe.rows) if row['component'] == gate['component'])
                    failed.append(dict(component=gate['component'], norad=gate['norad'],
                        conditional=gate['conditional_residual_gate'], profile_RMS_hz=gate['profile_rms_hz'],
                        profile_bias_hz=gate['profile_bias_hz'], aliases_changed=gate['aliases_changed'],
                        minimum_elevation_deg=float(elevation[probe.slices[slot]].min()),
                        family_has_shape_modes=gate['candidate_index'] in probe.supported,
                        conditionally_passing_owner_count=len(owners.get(gate['candidate_index'], ())),
                        family_support_needs_two_owners=gate['candidate_index'] in probe.supported))
                failures.append(dict(case=case, arm=arm, additions=json.dumps(trial['additions']),
                    new_points=trial['added_curved_points'], paired_valid=trial['paired_valid'],
                    phase_change_s=r['final_phase_change_s'], failing_curved_tracks=json.dumps(failed),
                    failing_predictive_tracks=json.dumps([t for t in r['linear_gates'] if not t['compatible']])))
        controls.extend(dict(case=case, **r) for r in current_dbg_figures(case))
        families.extend(family_rows(case, d))
        audit = read(RAW/case/'DBG01/audit.json')
        diagnoses[case] = dict(coverage_ceiling=ceilings[case],
                               decomposition={a:r['endpoint']['decomposition'] for a, r in audit['arms'].items()},
                               reference_decomposition={a:r['diagnostic_point']['decomposition'] for a, r in audit['arms'].items()},
                               RF_restart_selection=read(RAW/case/'DBG01/RF_restart_selection.json'),
                               restart_summary=read(RAW/case/'DBG01/restart_summary.json'))
    csv_write(OUT/'tables/position_and_association.csv', rows)
    csv_write(OUT/'tables/family_ablations.csv', families)
    csv_write(OUT/'tables/failed_reentry_gates.csv', failures)
    csv_write(OUT/'tables/all_interventions.csv', controls)
    csv_write(OUT/'tables/residual_diagnostics.csv', residuals)
    overview(rows, ceilings)
    nomination_and_graph_figures(cases)
    write(OUT/'evidence/evaluation.json', dict(rows=rows, ceilings=ceilings, diagnoses=diagnoses,
          no_ALGO_version_promoted=True, prototype_not_generalized_to_full_DS23=True,
          no_stationary_pooling_or_motion_prototype=True))
    for name in ['protocol.json', 'independent_iteration_audit.json', 'RF_restart_selection.json',
                 'DBG01_analysis_execution.json', 'DBG01_audit_discover_execution.json']:
        shutil.copyfile(RAW/name, OUT/'evidence'/name)
    for case in cases:
        target = OUT/'evidence'/case
        target.mkdir(exist_ok=True)
        for name in ['inventory.json', 'screen.json']:
            shutil.copyfile(RAW/case/name, target/name)
        for name in ['nominations', 'audit', 'positions']:
            shutil.copyfile(REENTRY/(case+'_'+name+'.json'), target/(name+'.json'))
        for name in ['request.json', 'protocol.json', 'interventions.csv', 'restart_comparison.csv',
                     'restart_summary.json', 'audit.json', 'hypothesis_bank.json', 'surface_values.json']:
            shutil.copyfile(RAW/case/'DBG01'/name, target/('DBG01_'+name if name == 'audit.json' else name))
        if (SUPPORT/(case+'_audited.json')).exists():
            shutil.copyfile(SUPPORT/(case+'_audited.json'), target/'support_aware_audit.json')
    for name in ['protocol.json', 'finalization_protocol.json', 'finalization_audit.json']:
        shutil.copyfile(SUPPORT/name, OUT/'evidence'/('support_'+name))
    tools = ['probe_ds23_worst_association_bottleneck.py', 'plot_ds23_worst_association_bottleneck.py',
             'probe_ds23_single_curved_reentry.py', 'run_dbg01_latest_worst.py',
             'audit_ds23_worst_iteration.py', 'select_dbg01_regional_restart.py',
             'ds23_active_mode_support.py', 'probe_ds23_support_aware_reentry.py',
             'finalize_ds23_support_reentry.py', Path(__file__).name]
    tests = ['test_ds23_worst_association_bottleneck.py', 'test_ds23_single_curved_reentry.py',
             'test_ds23_active_mode_support.py', 'test_report_ds23_dbg01_iteration_001.py']
    for name in tools:
        shutil.copyfile(ROOT/'tools'/name, OUT/'source/tools'/name)
    for name in tests:
        shutil.copyfile(ROOT/'tests/analysis'/name, OUT/'source/tests'/name)
    write(OUT/'evidence/artifact_hashes.json', {str(p.relative_to(OUT)):sha(p)
          for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'artifact_hashes.json' and p.suffix != '.log'})
    print('Iteration001 figures and tables generated:', OUT, flush=True)


if __name__ == '__main__':
    main()
