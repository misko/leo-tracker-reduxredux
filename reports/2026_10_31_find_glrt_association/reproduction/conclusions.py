"""Summarize completed 2x2 search and preserve qualified scientific conclusions."""
import argparse
import csv
import hashlib
import subprocess
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from investigate import read,write,PRODUCTION,INVENTORY,digest
from render import fails

NOTES={
('DS26-0265',4):('Supported identity; model inadequate','66102 remains preferred; independent family predicts 110 Hz. Residual curvature/step remain; wider phase adds a closer competitor.'),
('DS26-0092',6):('Supported identity; model inadequate','58788 is stable; residual time correlation survives both TLE banks and independent-family prediction.'),
('DS26-0158',2):('Tentative identity','66445 is preferred and independently supported, but historical nomination was ambiguous and broad search exposes 61918; correlated residuals remain.'),
('DS26-0251',4):('Model-sensitive','65894 is preferred. About -11.7 Hz/s is needed to reach 153 Hz RMS under wider priors; no independent active family supports that correction.'),
('DS26-0110',2):('Supported identity; model inadequate','64172 is independently supported; very low RMS does not remove residual correlation.'),
('DS26-0010',2):('Supported identity; model inadequate','65208 is stable with independent family support; slope, curvature, step and correlation remain.'),
('DS26-0068',7):('Strong new catalogue nomination','58538 was excluded by 48h age cutoff (52.12h). General 72h search recovers it; residual correlation still fails. Previous 63573 nomination was incomplete-catalogue evidence.'),
('DS26-0008',5):('Supported identity; model inadequate','66562 remains preferred; later TLE does not remove step/correlation. One saved alias transition is preserved.'),
('DS26-0062',3):('Strong new catalogue nomination','67821 was excluded by 48h age cutoff (50.65h). General 72h search gives 63 Hz RMS with diagnostic noise checks passing; independent identity/inclusion validation remains.'),
('DS26-0134',5):('Strong nomination; phase-model sensitive','59642 needs causal phase -27.18s, outside the old ±15s box. ±35s general search gives 75 Hz RMS; later TLE also nominates 59642. Correlation remains.'),
('DS27-0020',4):('Supported identity; model inadequate','61549 is supported by shared family prediction: 104 Hz versus 4727 Hz for 62146. Isolated-curve fits alone are ambiguous; curvature/step remain.'),
('DS27-0016',5):('Supported identity; shared-model mismatch','63899 fits in isolation at 75 Hz but independent shared prediction is 110 Hz and fails structure checks. Original joint rejection is not disproved by the isolated fit.'),
('DS27-0022',4):('Ambiguous','59737 leads; 63477 is close in the isolated score and 54159 wins some random groups. No independent calibrated family resolves the main alternatives.'),
('DS27-0022',3):('Supported identity; model inadequate','57914 is independently supported; target-only 103 Hz versus shared 140 Hz. Slope/curvature/step remain.'),
('DS27-0020',1):('Ambiguous','67344 leads, but expanding phase reduces the score gap to 50173 from 289 to 1.5. Shared support favors 67344; 50173 lacks an independent family, so uniqueness is unresolved.'),
('DS27-0002',8):('Strong new shared-model nomination','100427 gives 16 Hz using the already calibrated shared physical model, with diagnostic noise checks passing and 85 independent support points. Previously no retained search result; exact additive ownership replay still needed.'),
('DS27-0018',8):('Promising new nomination','58121 gives 106 Hz and passes isolated diagnostic checks. Historical recovery was incomplete; no independent active family yet validates identity.'),
('DS27-0012',2):('Ambiguous','57999 and 63782 remain competitive despite 22 Hz RMS; randomized groups disagree. Low residual is not uniqueness.'),
('DS27-0020',8):('Tentative identity','55430 leads this frozen-calibration search; previous independent nomination swapped with 51969. A near-threshold isolated pass does not resolve that disagreement.'),
('DS27-0020',6):('Supported identity; model inadequate','63813 independent shared prediction is 125 Hz; competing calibrated families miss by thousands of Hz. Residual correlation remains.'),
}


def main(out):
    table=[];summary=[];ablation=[]
    for row in read(out/'targets.json'):
        d=next(r for r in read(out/'cases'/row['case']/'expanded_search.json') if r['source']['fragment_id']==row['fragment_id'])
        chosen=next(r for r in d['summaries'] if r['age_limit_h']==72 and r['phase_limit_s']==35 and r['model']=='phase_small_rate' and r['arm']=='fitted_c');best=chosen['best']
        status,note=NOTES[row['case'],row['channel']];name=row['key'].split('-RF')[0].replace('SCAN-','');stem=row['case']+'-'+name
        shared=next(r for r in read(out/'cases'/row['case']/'shared_competitors.json') if r['source']['fragment_id']==row['fragment_id'])
        shared_best=next((r for r in shared['predictions'] if r['arm']=='fitted_c' and r['norad']==best['norad'] and 'rms_hz' in r),None)
        r=dict(case=row['case'],track=name,points=row['points'],best_causal_hypothesis=best['norad'],runner_up=chosen['runner_up']['norad'],target_fit_rms_hz=best['rms_hz'],independent_shared_rms_hz=shared_best['rms_hz'] if shared_best else None,phase_s=best['phase_s'],extra_rate_hz_s=best['rate_hz_s'],identity_status=status,explanation=note,remaining_diagnostic_failures=fails(best,row['points']),score_gap_not_probability=chosen['score_margin'])
        summary.append(r)
        rms=f'{best["rms_hz"]:.0f}'
        if row['case']=='DS27-0002':rms+=f' / **{shared_best["rms_hz"]:.0f} shared**'
        table.append(f'| {row["case"]} | [{name}](figures/{stem}.png) | {row["points"]} | {best["norad"]} | {rms} | {status} | {note} |')
        for cell in d['summaries']:
            ablation.append(dict(case=row['case'],track=name,age_limit_h=cell['age_limit_h'],phase_limit_s=cell['phase_limit_s'],arm=cell['arm'],model=cell['model'],norad=cell['best']['norad'],rms_hz=cell['best']['rms_hz'],phase_s=cell['best']['phase_s'],extra_rate_hz_s=cell['best']['rate_hz_s'],runner_up=cell['runner_up']['norad'],score_margin=cell['score_margin']))
    for name,rows in [('best_associations.csv',summary),('age_phase_ablation.csv',ablation)]:
        with (out/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(out/'best_associations.json',summary)
    (out/'findings.md').write_text('# Best hypotheses for all 20 residual sources\n\nRMS is the target-only phase + small-rate diagnostic after the general 72h/±35s search, except the explicitly labeled shared-model value. Identity support and residual/model adequacy remain separate. None of these rows is a new production acceptance.\n\n| Scan | Source | Points | Best causal hypothesis | RMS Hz | Identity assessment | Finding |\n| --- | --- | ---: | ---: | ---: | --- | --- |\n'+'\n'.join(table)+'\n\nThe detailed atlas contains original 48h/±15s and later-TLE comparisons. Expanded-search results are in `age_phase_ablation.csv` and each scan’s `expanded_search.json`. Companion `*-support.png` figures show paired catalogue/model comparisons and independent-family predictions.\n')
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained');labels=['48h / ±15s','48h / ±35s','72h / ±15s','72h / ±35s']
    for ax,case in zip(axes,['DS26-0068','DS26-0062','DS26-0134']):
        rows=[r for r in ablation if r['case']==case and r['arm']=='fitted_c' and r['model']=='phase_small_rate']
        ax.bar(range(4),[r['rms_hz'] for r in rows],color=['.65','#bd9c42','#568ecb','#23723c'])
        for i,r in enumerate(rows):ax.text(i,r['rms_hz']+20,f"{r['rms_hz']:.0f} Hz\n{r['norad']}",ha='center',fontsize=8)
        ax.set_xticks(range(4),labels,rotation=25,ha='right');ax.set(ylabel='RMS (Hz)',title=case,ylim=(0,max(r['rms_hz'] for r in rows)*1.25))
    fig.suptitle('Causal catalogue age × phase-search ablation — fixed published position, same native points');fig.savefig(out/'figures/age-phase-ablation.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(2,1,figsize=(15,9),layout='constrained')
    for ax,ds in zip(axs,['DS26','DS27']):
        ss=[r for r in summary if r['case'].startswith(ds)];xx=np.arange(len(ss))
        ax.bar(xx-.16,[r['target_fit_rms_hz'] for r in ss],width=.32,color='#176bbb',label='Target-only phase + small rate')
        use=[(i,r) for i,r in enumerate(ss) if r['independent_shared_rms_hz'] is not None]
        ax.bar([i+.16 for i,r in use],[r['independent_shared_rms_hz'] for i,r in use],width=.32,color='#d98721',label='Independent shared family model')
        ax.set_xticks(xx,[r['case'].replace(ds+'-','')+' '+r['track'].replace('RX1-','').replace('RX2-','R2 ') for r in ss],rotation=25,ha='right')
        ax.set(title=ds,ylabel='RMS (Hz)');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Best causal hypotheses after the diagnostic age/phase expansion — missing bars mean no independent family');fig.savefig(out/'figures/best-causal-fit-summary.png',dpi=160);plt.close(fig)
    files={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name!='run_manifest.json' and p.suffix not in ['.pyc','.log']}
    tools={str(p):digest(p) for root in [PRODUCTION/'tools',PRODUCTION/'src/leo/analysis/research'] for p in root.glob('*.py')}
    receipts=[read(p) for p in (out/'cases').glob('*/receipt.json')]
    write(out/'run_manifest.json',dict(skill='find-glrt-association',date='2026-10-31',targets=20,unique_native_points=sum(r['points'] for r in summary),scans=len(receipts),
        inference_code_revision=subprocess.check_output(['git','-C',str(PRODUCTION),'rev-parse','HEAD'],text=True).strip(),
        source_checkout=str(PRODUCTION),python=sys.version,files_sha256=files,numerical_source_sha256=tools,
        models={'phase_offset':dict(noise_hz=150,bias_prior_sigma_hz=300,phase_prior_sigma_s=5), 'phase_small_rate':dict(extra_rate_prior_sigma_hz_s=.5),'phase_wider_rate':dict(extra_rate_prior_sigma_hz_s=2,bias_prior_sigma_hz=1000),'affine_control':dict(extra_rate_prior_sigma_hz_s=30,bias_prior_sigma_hz=1e6)},
        validation=dict(group_seconds=12,guard_seconds=2,seeds=[20261031,94721,4081],conditional_on_full_data_shortlist=True,calibration_excludes_all_20_targets=True),
        expanded_search=dict(age_hours=[48,72],phase_bounds_seconds=[15,35],position_fixed_to_published_per_arm=True,held_validation_of_new_expanded_nominees=False),
        causal_and_later_separate=True,truth_used=False,position_refitted=False,production_owners_changed=False,new_associated_points=0,
        causal_baseline_replay_errors={r['case']:r['baseline_objective_replay'] for r in receipts}))
    print('Wrote final associations, controlled ablation, summary figures and run manifest.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
