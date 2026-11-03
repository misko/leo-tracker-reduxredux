"""Scientific pilot figures, generated only from replayed results and RF slices."""

import numpy as np

from probe_ds23_multilane_position import prepare_inputs, OUT as CUT, make as cut_make
from probe_ds23_joint_multilane_position import OUT as JOINT, make as joint_make
from probe_ds23_0289_weak_RF import OUT as WEAK
from run_algo01_ds23_sample import ROOT, read, write

OUT = ROOT/'reports/2026_10_20_ds23_multilane_position'


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    audit = read(OUT/'independent_replay_audit.json')
    methods = ['incumbent', 'RF_refined_control', 'shared_single_lane', 'shared_all_lanes', 'joint_shared_all_lanes']
    names = ['Incumbent', 'RF refinement', 'One pair', 'All pairs:\npredictive', 'All pairs:\njoint curved']
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), constrained_layout=True)
    for case, ax in zip(['DS23-0202', 'DS23-0274', 'DS23-0154'], axes, strict=True):
        for arm, shift in [('c0', -.18), ('fitted_c', .18)]:
            rows = [next(r for r in audit['rows'] if (r['case'], r['method'], r['arm']) == (case, m, arm)) for m in methods]
            bars = ax.bar(np.arange(len(methods))+shift, [r['policy_position_error_km'] for r in rows], width=.34, label=arm)
            ax.bar_label(bars, fmt='%.3f', fontsize=7)
            for k, r in enumerate(rows):
                if not r['paired_valid']:
                    bars[k].set_hatch('//')
                    ax.scatter(k+shift, r['trial_position_error_km'], marker='x', c='red', s=25, zorder=4)
        ax.set(xticks=np.arange(len(methods)), xticklabels=names, ylabel='Position error (km)', title=case)
        ax.tick_params(axis='x', labelrotation=15); ax.set_ylim(0, ax.get_ylim()[1]*1.2); ax.legend(ncol=2, fontsize=7); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Three development scans: multi-channel evidence can strengthen position inference\nHatched bars retain original incumbent; red crosses are rejected trials; both c arms use matched data/priors')
    fig.savefig(OUT/'pilot_position_comparison.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    residuals = []
    for case, ax in zip(['DS23-0202', 'DS23-0274'], axes, strict=True):
        d = prepare_inputs(case); cut = read(CUT/(case+'.json')); joint = read(JOINT/(case+'.json'))
        old = cut['results']['shared_all_lanes']['arms']['fitted_c']; new = joint['results']['joint_shared_all_lanes']['arms']['fitted_c']
        p = cut_make(d, 'fitted_c', np.asarray(old['phase_reference']), cut['results']['shared_all_lanes']['entries'], True)
        q = joint_make(d, 'fitted_c', np.asarray(new['phase_reference']), joint['extra_entries'], True)
        before, after = p.calculate(old['endpoint_east_north_km']), q.calculate(new['endpoint_east_north_km'])
        component = case+'_RX1_CH4-second'
        k = next(k for k, e in enumerate(p.linear_entries) if e['component'] == component); sl = p.linear_slices[k]
        time = p.scan.tracks[p.linear_entries[k]['track_index']]['times']
        y = before['linear_raw_prediction_residual_hz'][sl]; y = y-y.mean()
        k = next(k for k, e in enumerate(q.joint_secondary_entries) if e['component'] == component); sl = q.joint_secondary_slices[k]
        z = after['joint_secondary_fitted_residual_hz'][sl]
        ax.plot(time, y, '.-', lw=.8, label='Predictive-only calibration, mean removed')
        ax.plot(time, z, '.-', lw=.8, label='Joint independently curved calibration')
        ax.axhline(0, color='k', lw=.5); ax.legend(fontsize=7); ax.grid(alpha=.2)
        ax.set(title=case+' · RX1 CH4 secondary', xlabel='Scan time (s)', ylabel='Conditional residual (Hz)')
        residuals.append(dict(case=case, component=component, time_s=time, predictive_residual_hz=y, joint_residual_hz=z))
    fig.suptitle('A newly curved fragment can update calibration; linear fragments remain predictive-only\nScan274 still fails an unchanged gate on another original track, so its joint trial is rejected')
    fig.savefig(OUT/'secondary_calibration_residuals.png', dpi=160); plt.close(fig)
    write(OUT/'secondary_calibration_residuals.json', dict(rows=residuals, no_GPS_used=True, raw_predictive_means_removed_for_plot_only=True))
    weak = read(WEAK/'evaluation.json'); diagnostic = read(ROOT/'reports/2026_10_20_ds23_joint_probe_position_v2/DS23-0289_tail_native_peaks.json')
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    for r, ax in zip(sorted(weak['rows'], key=lambda r: r['time_s']), axes, strict=True):
        archived = r['archived_CFO_hz']; reference = next(s for s in diagnostic['rows'] if s['probe'] == r['probe'])
        ax.plot(np.array(r['grid_CFO_hz'])-archived, r['conditional_RF_scores'])
        ax.axvline(r['wide_fit']['CFO_hz']-archived, color='tab:green', label='RF-only wide fit')
        ax.axvline(-reference['original_residual_hz'], color='tab:red', ls='--', label='RF-position orbit prediction')
        ax.set(xlim=(-2000, 1000), xlabel='CFO minus archived winner (Hz)', ylabel='Known-pilot profile score', title=f"t={r['time_s']:.2f}s · margin {r['archived_margin']:.3f}")
        ax.legend(fontsize=7); ax.grid(alpha=.2)
    fig.suptitle('DS23-0289: the weak endpoint frequency is supported by the saved IQ\nSlices condition on wide-fit epoch/rate; the orbit marker was not a search seed; these are not calibrated probabilities')
    fig.savefig(OUT/'weak_endpoint_RF_slices.png', dpi=160); plt.close(fig)


if __name__ == '__main__':
    main()
