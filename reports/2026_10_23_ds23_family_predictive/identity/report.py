"""Report fixed RF-position comparisons without evaluation coordinates."""
from pathlib import Path
import json
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent

def main():
    rows=[];inputs={}
    for family in [65340,67618]:
        for arm in ['c0','fitted_c']:
            for position in ['graph_parent','native_RF_endpoint']:
                path=OUT/f'{family}_{arm}_{position}.json';d=json.loads(path.read_text());assert d['status']=='complete' and d['calibration_phase_converged']
                inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
                old=d['original'];alts=[c for c in d['candidates'] if c['norad']!=family];qualified=[c for c in alts if c['qualified']];strict=[c for c in alts if c['physical_and_residual_qualified']]
                brief=lambda c:dict(norad=c['norad'],score=c['score'],delta_score_vs_original=c['score']-old['score'],qualified=c['qualified'],physical_and_residual_qualified=c['physical_and_residual_qualified'],phase_s=c['phase_s']) if c else None
                rows.append(dict(family=family,arm=arm,position=position,original_score=old['score'],original_qualified=old['qualified'],original_physical_and_residual_qualified=old['physical_and_residual_qualified'],
                    original_phase_s=old['phase_s'],best_alternative=brief(alts[0]),best_physical_alternative=brief(qualified[0]) if qualified else None,best_physical_and_residual_alternative=brief(strict[0]) if strict else None,
                    calibration_points=d['calibration_points'],removed_calibration_points=d['removed_calibration_points'],native_points=len(d['held_observation_ids']),native_paths=len(d['members']),seconds=d['seconds'],coarse_top10=d['coarse_top10']))
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for col,family in enumerate([65340,67618]):
        rr=[r for r in rows if r['family']==family];x=np.arange(len(rr))
        axes[col].bar(x,[r['best_alternative']['delta_score_vs_original'] for r in rr],color='#a4a4a4',label='Best refined (may fail gates)')
        axes[col].scatter(x,[r['best_physical_alternative']['delta_score_vs_original'] if r['best_physical_alternative'] else np.nan for r in rr],color='#285b93',s=45,label='Best physical-qualified')
        axes[col].axhline(0,c='black',lw=.8);axes[col].set_xticks(x,[r['arm']+'\n'+r['position'].replace('_',' ') for r in rr],fontsize=8)
        axes[col].set(title=f'Native family {family}',ylabel='Alternative minus original score (positive favors original)');axes[col].legend(fontsize=8,loc='center right')
    fig.suptitle('Common union-family calibration holdout; every identity receives fresh phase + physical-mode priors\nFrozen RF endpoints; no GPS, position refit or out-of-sample accuracy claim')
    fig.savefig(OUT/'symmetric_margins.png',dpi=180);plt.close(fig)
    compact=dict(rows=rows,total_job_seconds=sum(r['seconds'] for r in rows),all_terminal=True,all_calibration_phase_converged=True,input_hashes=inputs,
        comparison='Score deltas only within the new common holdout + fresh physical prior model. No score deltas against previous asymmetric screens.',
        limitation='Withheld-family curved points excluded rather than tested; evidence comprises target native paths. Fixed RF positions were fitted using original evidence; this is position-conditioned sensitivity, not crossvalidation. Original and replacements have no calibrated phase/mode advantage, but remaining radio posterior is conditional on other retained graph identities. Finite frozen shortlist, Gaussian phase-moment approximation, independently proposed path aliases, causal physical-mode approximation.1338 coarse phase-only output is diagnostic, not exhaustive physical fit.')
    (OUT/'compact.json').write_text(json.dumps(compact,indent=2)+'\n')
    text=['# DS23-0259 symmetric withheld-family native prediction','',
        'All eight bounded jobs completed, with converged fixed-position calibration phase refreshes. The calibration mask removes every retained curved point assigned any identity in the frozen target-specific union shortlist. Every candidate—including the original—then uses a fresh causal phase prior and three physical orbit modes with zero mean and unit variance. No fitted original phase or mode coefficient enters its predictive prior. Radio uncertainty is shared within each comparison. This is a new common physical prior policy, including candidates that previously received phase-only uncertainty.',
        '', 'The original identity has the lowest score in every context under this symmetric common model, and passes physical plus fixed-radio residual gates. No alternative passes both sets of gates. For65340, the nearest alternative62890 is worse by36.98–39.22 score units and exceeds the phase bound; the best physically qualified62754 is worse by85.32–86.09 and fails residual gates. For67618, nearest58744 is worse by624.61–658.00 and exceeds the phase bound; best physically qualified57079 is worse by743.88–802.34 and fails residual gates.',
        '', '| Family | Arm | Fixed RF position | Calibration retained/withheld | Native paths/points | Original score | Best alternative (delta) | Physically qualified? |', '|---|---|---|---|---|---|---|---|']
    for r in rows:
        a=r['best_alternative'];text.append(f"| {r['family']} | {r['arm']} | {r['position']} | {r['calibration_points']}/{r['removed_calibration_points']} | {r['native_paths']}/{r['native_points']} | {r['original_score']:.3f} | {a['norad']} ({a['delta_score_vs_original']:+.3f}) | {a['qualified']} |")
    text += ['',compact['comparison'],'',compact['limitation'],'',
        'Physical qualification applies the same ±15s phase, nonnegative elevation and ≤0.01s phase-convergence rules to all identities. Fixed-radio per-path residual/noise gates are reported separately; no predictive observation calibrates the radio posterior. The all1338 causal entries receive a phase-only coarse diagnostic screen, while exact phase + physical-mode refinement uses only the pre-frozen union shortlist. Newly nominated coarse objects are visible in compact.json but are not silently added without the matching calibration holdout.',
        '', 'No localization accuracy or external satellite-identity confirmation is claimed. Inputs, prior matrices, held/calibration ID vectors, candidate scores and diagnostic gates are retained in per-job JSON. No new RF, future TLE, position optimization or publication occurred.', '', '![Symmetric predictive score margins](symmetric_margins.png)','']
    (OUT/'REPORT.md').write_text('\n'.join(text))
    helperroot=Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools')
    sources=[OUT/'study.py',OUT/'report.py',OUT/'test_study.py',OUT/'protocol.json']+[helperroot/name for name in ['build_dsx01_orbit_modes.py','probe_ds23_linear_family_groups.py','ds23_conditioned_relative_nomination.py','ds23_temporal_predictive_recovery.py','ds23_family_cavity.py']]
    (OUT/'source_receipt.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2)+'\n')

if __name__=='__main__':main()
