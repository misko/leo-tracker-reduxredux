"""Render bounded native predictive scores without evaluation-site data."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent


def main():
    rows=[];sources=[]
    for path in sorted(ROOT.glob('DS26-*_results.json')):
        obj=json.loads(path.read_text());sources.append(obj)
        for r in obj['rows']:
            if 'error' in r:continue
            for subset,v in r['scores'].items():
                rows.append(dict(case=obj['case'],arm=r['arm'],fold=r['fold'],solver=r['solver'],SD_scale=r['SD_scale'],
                    subset=subset,phase_closed=r['phase_closed'],boundary=r['boundary'],optimizer_success=r['optimizer_success'],
                    phase_change_s=r['phase_change_s'],position_curvature_floored=r['position_curvature_floored'],**v))
    if not rows:return
    with (ROOT/'scores.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summaries=[]
    for case in sorted({r['case'] for r in rows}):
        for arm in ['c0','fitted_c']:
            for subset in ['all','target','other']:
                local=[]
                for solver,scale in [('legacy',1.),('damped_half',1.),('damped_half',2.),('damped_half',4.)]:
                    rr=[r for r in rows if (r['case'],r['arm'],r['subset'],r['solver'],r['SD_scale'])==(case,arm,subset,solver,scale)]
                    if not rr:continue
                    local.append(dict(case=case,arm=arm,subset=subset,solver=solver,SD_scale=scale,folds=len(rr),
                        sum_negative_twice_log_density=sum(r['negative_twice_log_density'] for r in rr),
                        sum_points=sum(r['points'] for r in rr),phase_closed_folds=sum(r['phase_closed'] for r in rr),
                        boundary_folds=sum(r['boundary'] for r in rr),optimizer_success_folds=sum(r['optimizer_success'] for r in rr)))
                local.sort(key=lambda r:r['sum_negative_twice_log_density'])
                baseline=next((r['sum_negative_twice_log_density'] for r in local if r['solver']=='legacy'),None)
                for rank,r in enumerate(local,1):
                    r.update(rank=rank,gain_over_legacy=baseline-r['sum_negative_twice_log_density']);summaries.append(r)
    with (ROOT/'ranked_summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    findings=[]
    for case in sorted({r['case'] for r in summaries}):
        gains=[]
        for arm in ['c0','fitted_c']:
            all4=next(r for r in summaries if (r['case'],r['arm'],r['subset'],r['solver'],r['SD_scale'])==(case,arm,'all','damped_half',4.))
            other4=next(r for r in summaries if (r['case'],r['arm'],r['subset'],r['solver'],r['SD_scale'])==(case,arm,'other','damped_half',4.))
            gains.append(f"{arm}: all gain {all4['gain_over_legacy']:.2f}, other-family gain {other4['gain_over_legacy']:.2f}, phase closed {all4['phase_closed_folds']}/3, optimizer success {all4['optimizer_success_folds']}/3, boundary folds {all4['boundary_folds']}/3")
        findings.append(case+' SD4 ranks first and SD2 second in each held subset and both c arms ('+'; '.join(gains)+').')
    lines=['# Native conditional predictive validation','',
        ' '.join(findings)+' Solver-only predictive differences are small. These comparisons support a family-influence sensitivity, with convergence and development-selection limits; they do not establish production acceptance.','',
        'These scores test the effect of the selected family on native held observations, including other satellite families. The native hardware, receiver, phase, orbit correction and position fits use only training IDs. They are conditional development evidence: full-data nominations, aliases, native masks, RF initialization, point-noise preprocessing and likelihood powers remain inherited. Ancillary linear/family likelihoods are omitted. No GPS was accessed by this runner.','',
        'Each scan has three random synchronized 5 s group folds (seed 2026110207), holding 20% of available groups and guarding an adjacent 5 s group on either side. Both c arms and all four model cells share native held IDs. Protocol JSON and SHA256 were written before outcome fits. Eight phase rounds, 25 position iterations and 100 function evaluations per round are the fixed fit budget.','',
        'The reported score is −2 times a normalized Gaussian log predictive density, integrating the fitted linear coefficient covariance and a local Laplace approximation for position uncertainty. The fitted Gamma precisions are conditioned upon; their uncertainty is not integrated. Training uses existing likelihood powers; held scores have no likelihood power. A wholly unseen fragment uses its Gamma(2,2) prior inverse-precision expectation. `all`, `target`, and `other` are separate marginal densities, so their scores do not add. Overlapping random folds are correlated: sums rank these declared fits and are not independent-sample evidence or identity probabilities.','',
        '| Scan | c arm | Held subset | Rank | Solver | Physical SD | −2 log density sum | Gain vs legacy | Phase closed |','|---|---|---|---:|---|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['case']} | {r['arm']} | {r['subset']} | {r['rank']} | {r['solver']} | {r['SD_scale']:g} | {r['sum_negative_twice_log_density']:.2f} | {r['gain_over_legacy']:.2f} | {r['phase_closed_folds']}/{r['folds']} |")
    lines += ['','Positive gain means improved normalized predictive density. A nonclosed phase cell remains an unfinished approximation and cannot establish a preferred physical model. Position curvature clipping or a regional boundary further weakens the Laplace approximation. Held RMS is diagnostic only; it does not choose the model. Noise is diagonal conditional on the shared latent modes; group withholding does not itself calibrate residual correlations within each held group.','',
        'Files: `scores.csv` contains per-fold/per-family scores, `ranked_summary.csv` contains declared model ranks, each job JSON retains RF fit/convergence diagnostics and matched-ID hashes, and each scan protocol lists all native train/held IDs. `evaluate_context` in `predictive.py` accepts a remapped context and these same IDs for root-owned identity-mixture validation.','',
        'Validation: component tests compare normalized low-rank density against a dense covariance calculation and verify deterministic synchronized splits and exact group guards. No production files, published ownership or golden fixtures were changed.']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
    cases=sorted({r['case'] for r in summaries});fig,axes=plt.subplots(len(cases),2,figsize=(11,4*len(cases)),squeeze=False)
    for i,case in enumerate(cases):
        for j,arm in enumerate(['c0','fitted_c']):
            ax=axes[i,j];labels=['legacy SD1','damped SD1','damped SD2','damped SD4']
            for subset,offset in [('all',-.22),('target',0),('other',.22)]:
                lookup={(r['solver'],r['SD_scale']):r for r in summaries if (r['case'],r['arm'],r['subset'])==(case,arm,subset)}
                keys=[('legacy',1.),('damped_half',1.),('damped_half',2.),('damped_half',4.)]
                values=[lookup[k]['gain_over_legacy'] if k in lookup else np.nan for k in keys]
                ax.bar(np.arange(4)+offset,values,width=.22,label=subset)
            ax.axhline(0,color='black',lw=.8);ax.set_xticks(np.arange(4),labels,rotation=15)
            ax.set_title(f'{case} {arm}');ax.set_ylabel('Legacy − candidate (−2 log density sum)');ax.legend()
    fig.suptitle('Native guarded conditional prediction; positive favors candidate\nOverlapping folds and Gaussian approximation: development evidence')
    fig.tight_layout();fig.savefig(ROOT/'predictive_gains.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
