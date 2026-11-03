"""Compare held-frame phase slopes with independent within-frame RF fits.

Phase slopes do not automatically measure physical carrier Doppler. The local
Gaussian scale is a conditional diagnostic, not a calibrated rejection test.
"""

from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_phase_RF_consistency'


def main():
    OUT.mkdir(exist_ok=True)
    phase_path = ROOT/'reports/2026_10_21_ds23_fractional_differential_phase/evaluation.json'
    rf_path = ROOT/'reports/2026_10_21_ds23_joint_component_refinement/evaluation.json'
    phases, radio = read(phase_path), read(rf_path)
    lookup = {(r['case'],r['probe']):r for r in phases['rows'] if r['status'] == 'complete'}
    rows = []
    for r in radio['rows']:
        if r['status'] != 'complete': continue
        phase = lookup[r['case'],r['probe']]['models']['differential']
        h = next(v for v in phase['harmonics'] if v['harmonic'] == phase['best_harmonic'])
        contrast = np.array([1.,0,0,-1,0,0])
        change = float(np.array(r['CFO_delta_hz'])@np.array([1.,-1.]))
        sigma = float(np.sqrt(contrast@np.array(r['local_Gaussian_parameter_covariance'])@contrast))
        rows.append(dict(case=r['case'],group=r['group'],probe=r['probe'],
            phase_slope_hz=h['residual_frequency_hz'],joint_RF_difference_change_hz=change,
            local_joint_RF_difference_sigma_proxy_hz=sigma,
            discrepancy_in_local_RF_sigma=abs(h['residual_frequency_hz']-change)/sigma,
            phase_screen_candidate=phase['candidate_for_independent_replication'],
            strict_joint_RF_prediction_qualified=r['qualified_for_full_curve_test']))
    strong = [r for r in rows if r['phase_screen_candidate']]
    strict = [r for r in strong if r['strict_joint_RF_prediction_qualified']]
    write(OUT/'evaluation.json',dict(rows=rows,matched_probes=len(rows),strong_phase_screen=len(strong),
        strong_phase_within_three_local_RF_scales=sum(r['discrepancy_in_local_RF_sigma'] <= 3 for r in strong),
        strict_RF_and_strong_phase=len(strict),
        strict_RF_and_strong_phase_within_three_local_RF_scales=sum(r['discrepancy_in_local_RF_sigma'] <= 3 for r in strict),
        local_Gaussian_scales_not_calibrated_confidence=True,no_CFO_or_position_correction_applied=True,
        phase_continuity_not_equivalent_to_carrier_Doppler=True,
        exact_origin_of_large_frame_phase_slopes_not_established=True,
        sources={str(p.relative_to(ROOT)):sha(p) for p in [phase_path,rf_path,Path(__file__)]}))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7.5,6),constrained_layout=True)
    for label, subset, color in [('Other probes',[r for r in rows if not r['phase_screen_candidate']],'gray'),
        ('Strong held-frame phase',[r for r in strong if not r['strict_joint_RF_prediction_qualified']],'tab:orange'),
        ('Also passes joint RF prediction',strict,'tab:blue')]:
        ax.errorbar([r['phase_slope_hz'] for r in subset],[r['joint_RF_difference_change_hz'] for r in subset],
            yerr=[3*r['local_joint_RF_difference_sigma_proxy_hz'] for r in subset],fmt='o',ms=4,alpha=.65,label=label,color=color,lw=.7)
    ax.plot([-190,190],[-190,190],'k:',label='Equal carrier corrections');ax.axhline(0,color='gray',lw=.5)
    ax.set(xlabel='Inter-frame differential phase slope (Hz)',ylabel='Joint within-frame CFO difference correction (Hz)')
    ax.set_title('Frame phase slopes often disagree with physical within-frame carrier estimates\n46 RF-selected probes; error bars are 3× local Gaussian proxies, not calibrated intervals',fontsize=10)
    ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(OUT/'phase_vs_within_frame_RF.png',dpi=160);plt.close(fig)
    print('Matched',len(rows),'strong phase',len(strong),'within3',sum(r['discrepancy_in_local_RF_sigma'] <= 3 for r in strong),
          'strict overlap',len(strict),'strict within3',sum(r['discrepancy_in_local_RF_sigma'] <= 3 for r in strict),flush=True)


if __name__=='__main__':main()
