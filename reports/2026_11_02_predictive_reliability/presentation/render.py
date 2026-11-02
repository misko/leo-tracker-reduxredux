"""Presentation of sealed RF evidence only; no inference or geography reads."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm,ListedColormap
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parent
CASES=['DS26-0070','DS26-0309','DS26-0040','DS26-0044','FRSH-0004']
SPLITS=['time_f0','time_f1','time_f2','family_to_rx1','family_to_rx2']
LABELS=['Time 0','Time 1','Time 2','Target → RX1','Target → RX2']
ARMS=['c0','fitted_c']


def load():
    results=json.loads((REPORT/'predictive/results.json').read_text())
    decisions=json.loads((REPORT/'decisions.json').read_text())
    plan=json.loads((REPORT/'predictive/plan.json').read_text())
    digest=hashlib.sha256((REPORT/'predictive/results.json').read_bytes()).hexdigest()
    assert digest==decisions['results_sha256']
    assert all(v['verdict']=='inconclusive'for v in decisions['cases'].values())
    return results,decisions,plan


def tables(results,decisions,plan):
    index={(r['case'],r['split'],r['arm'],float(r['SD_scale'])):r for r in results['rows']}
    comparisons={(case,r['split'],r['arm']):r for case,v in decisions['cases'].items()for r in v['comparisons']}
    supports=[];scores=[];probes=[];qualifications=[]
    for case in CASES:
        record=next(c for c in plan['cases']if c['case']==case)
        for split in record['partitions']:
            name=split['name']
            supports.append(dict(case=case,target_family=record['family'],split=name,kind=split['kind'],eligible=split['eligible'],
                training_points=split['training_points'],held_points=split['held_points'],held_receiver=split.get('held_receiver'),
                opposite_receiver_target_points=split.get('opposite_receiver_target_points'),target_overlap_seconds=split.get('target_overlap_seconds'),
                other_calibration_families_by_band=json.dumps(split.get('other_receiver_calibration_families_by_band',{}),sort_keys=True),
                support_reasons=';'.join(split.get('ineligible_reasons',[]))))
            for arm in ARMS:
                pair=[index[(case,name,arm,sd)]for sd in [1.,4.]]
                comparison=comparisons.get((case,name,arm))
                row=dict(case=case,split=name,kind=split['kind'],arm=arm,supported=split['eligible'],
                    paired_four_fit_qualified=bool(comparison and comparison['paired_qualified']),
                    SD1_status=pair[0]['status'],SD4_status=pair[1]['status'],
                    SD1_qualified=pair[0].get('numerical_fit_qualified',False),SD4_qualified=pair[1].get('numerical_fit_qualified',False),
                    SD1_failure_reasons=';'.join(pair[0].get('unqualified_reasons',[])),SD4_failure_reasons=';'.join(pair[1].get('unqualified_reasons',[])))
                for subset in ['all','target','other']:
                    available=all(r['status']=='complete'and r['scores'][subset]['status']=='complete'for r in pair)
                    a,b=[r['scores'][subset]['bounded']['negative_twice_log_density']for r in pair]if available else [None,None]
                    row.update({subset+'_SD1_score':a,subset+'_SD4_score':b,subset+'_gain_SD4':a-b if available else None})
                if comparison:
                    assert np.isclose(row['all_gain_SD4'],comparison['gain_SD4'],rtol=0,atol=1e-9)
                    if comparison['other_family_gain_SD4']is not None:assert np.isclose(row['other_gain_SD4'],comparison['other_family_gain_SD4'],rtol=0,atol=1e-9)
                scores.append(row)
                for r in pair:
                    qualifications.append(dict(case=case,split=name,arm=arm,SD_scale=r['SD_scale'],status=r['status'],
                        qualified=r.get('numerical_fit_qualified',False),reasons=';'.join(r.get('unqualified_reasons',[]))))
                    for probe in r.get('local_gaussian_probes',[]):
                        probes.append(dict(case=case,split=name,arm=arm,SD_scale=r['SD_scale'],axis=probe['axis'],sign=probe['sign'],
                            inside_box=probe['inside_box'],objective_change=probe['training_negative_twice_objective_change'],pass_probe=probe['pass_probe']))
    return supports,scores,probes,qualifications


def csv_write(path,rows):
    with path.open('w')as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def heatmap(ax,scores,arm,subset,norm,cmap):
    matrix=np.full((5,5),np.nan);lookup={(r['case'],r['split']):r for r in scores if r['arm']==arm}
    for i,case in enumerate(CASES):
        for j,split in enumerate(SPLITS):
            row=lookup[(case,split)];value=row[subset+'_gain_SD4']
            if value is not None:matrix[i,j]=value
    im=ax.imshow(matrix,cmap=cmap,norm=norm,aspect='auto')
    for i,case in enumerate(CASES):
        for j,split in enumerate(SPLITS):
            row=lookup[(case,split)];value=row[subset+'_gain_SD4']
            if value is None:
                ax.text(j,i,'unsupported'if not row['supported']else'no other hold',ha='center',va='center',fontsize=8,color='#444444')
            else:
                text=f'{value:+.2f}'
                ax.text(j,i,text,ha='center',va='center',fontsize=10,color='white'if abs(value)>norm.vmax*.65 else'#111111')
                if not row['paired_four_fit_qualified']:ax.plot(j+.34,i-.28,marker='x',color='black',markersize=8,mew=1.8)
    ax.set_xticks(range(5),LABELS,rotation=18,ha='right');ax.set_yticks(range(5),CASES)
    ax.set_title(('c = 0'if arm=='c0'else'fitted c')+' · '+{'all':'joint held density','target':'target-family marginal','other':'other-family marginal'}[subset])
    return im


def gain_figures(scores):
    cmap=plt.get_cmap('RdBu').copy();cmap.set_bad('#dddddd')
    maxgain=max(abs(r['all_gain_SD4'])for r in scores if r['all_gain_SD4']is not None)
    norm=TwoSlopeNorm(vmin=-maxgain,vcenter=0.,vmax=maxgain)
    fig,axes=plt.subplots(1,2,figsize=(14,4.9),layout='constrained')
    for ax,arm in zip(axes,ARMS):im=heatmap(ax,scores,arm,'all',norm,cmap)
    fig.colorbar(im,ax=axes,shrink=.8,label='Gain in −2 log density (positive favors SD4)')
    fig.suptitle('Raw conditional RF prediction: all five strict decisions remain inconclusive',fontsize=14)
    fig.legend(handles=[Patch(facecolor='#dddddd',label='Unsupported transfer'),Line2D([0],[0],marker='x',color='black',lw=0,label='Paired numerical qualification failed')],loc='outside lower center',ncol=2)
    fig.savefig(ROOT/'joint_gain_heatmap.png',dpi=180);plt.close(fig)
    vals=[abs(r[k+'_gain_SD4'])for r in scores for k in ['target','other']if r[k+'_gain_SD4']is not None]
    marginal_norm=TwoSlopeNorm(vmin=-max(vals),vcenter=0.,vmax=max(vals))
    fig,axes=plt.subplots(2,2,figsize=(14,9.7),layout='constrained')
    for i,subset in enumerate(['target','other']):
        for ax,arm in zip(axes[i],ARMS):im=heatmap(ax,scores,arm,subset,marginal_norm,cmap)
    fig.colorbar(im,ax=axes.ravel().tolist(),shrink=.7,label='SD1 − SD4 (−2 log marginal predictive density)')
    fig.suptitle('Target and other-family predictions · marginal gains do not add to joint gain',fontsize=14)
    fig.legend(handles=[Patch(facecolor='#dddddd',label='Unsupported / no other held subset'),Line2D([0],[0],marker='x',color='black',lw=0,label='Paired numerical qualification failed')],loc='outside lower center',ncol=2)
    fig.savefig(ROOT/'marginal_gain_heatmaps.png',dpi=180);plt.close(fig)


def qualification_figure(rows):
    columns=[('c0',1.),('c0',4.),('fitted_c',1.),('fitted_c',4.)]
    lookup={(r['case'],r['split'],r['arm'],r['SD_scale']):r for r in rows}
    fig,axes=plt.subplots(1,5,figsize=(15,4.3),layout='constrained');cmap=ListedColormap(['#d9d9d9','#e8a46a','#64b891'])
    abbreviations={'position_optimizer_failed':'O','position_at_regional_boundary':'B','local_gaussian_objective_probes_failed':'P',
        'phase_not_closed':'Φ','inner_VI_precision_not_converged':'V'}
    for ax,case in zip(axes,CASES):
        matrix=np.zeros((5,4))
        for i,split in enumerate(SPLITS):
            for j,(arm,scale)in enumerate(columns):
                r=lookup[(case,split,arm,scale)];matrix[i,j]=0 if r['status']!='complete'else 2 if r['qualified']else 1
        ax.imshow(matrix,cmap=cmap,vmin=0,vmax=2,aspect='auto')
        for i,split in enumerate(SPLITS):
            for j,(arm,scale)in enumerate(columns):
                r=lookup[(case,split,arm,scale)]
                text='U'if r['status']!='complete'else'✓'if r['qualified']else''.join(abbreviations.get(v,'!')for v in r['reasons'].split(';')if v)
                ax.text(j,i,text,ha='center',va='center',fontsize=10)
        ax.set_title(case);ax.set_yticks(range(5),LABELS if ax is axes[0]else['']*5)
        ax.set_xticks(range(4),['c0\nSD1','c0\nSD4','fit c\nSD1','fit c\nSD4'],fontsize=8)
    fig.suptitle('Individual fit qualification · paired comparisons require all four fits to qualify',fontsize=13)
    fig.legend(handles=[Patch(facecolor='#64b891',label='✓ Numerical checks pass'),Patch(facecolor='#e8a46a',label='O optimizer; B boundary; P local-Gaussian probes'),Patch(facecolor='#d9d9d9',label='U unsupported transfer')],loc='outside lower center',ncol=3,fontsize=9)
    fig.savefig(ROOT/'qualification_grid.png',dpi=180);plt.close(fig)


def probe_figure(probes):
    labels=[];fractions=[];counts=[]
    for case in CASES:
        for arm in ARMS:
            for scale in [1.,4.]:
                rr=[r for r in probes if(r['case'],r['arm'],r['SD_scale'])==(case,arm,scale)]
                passed=sum(r['pass_probe']for r in rr);outside=sum(not r['inside_box']for r in rr)
                shape=len(rr)-passed-outside;labels.append(f"{case} · {'c0'if arm=='c0'else'fit c'} SD{scale:g}")
                fractions.append(np.array([passed,shape,outside])/len(rr));counts.append((passed,shape,outside,len(rr)))
    values=np.array(fractions);fig,ax=plt.subplots(figsize=(11,8.4),layout='constrained');left=np.zeros(len(labels));colors=['#64b891','#d58b7c','#8a75a1']
    for k,name in enumerate(['Passed','Inside box, objective rise outside [0.5,1.5]','Probe outside box']):
        ax.barh(np.arange(len(labels)),values[:,k],left=left,color=colors[k],label=name,height=.76);left+=values[:,k]
    for y,(passed,shape,outside,n)in enumerate(counts):ax.text(1.01,y,f'{shape+outside}/{n} failed',va='center',fontsize=8)
    for y in [3.5,7.5,11.5,15.5]:ax.axhline(y,color='#dddddd',lw=.8)
    ax.set_yticks(range(len(labels)),labels,fontsize=8);ax.invert_yaxis();ax.set_xlim(0,1.22)
    ax.set_xticks([0,.25,.5,.75,1.],['0%','25%','50%','75%','100%']);ax.set_xlabel('Fraction of four training-only covariance-axis probes per completed fit')
    ax.set_title('Local Gaussian credibility probes · no held observations enter these evaluations')
    fig.legend(loc='outside lower center',ncol=3,fontsize=8)
    fig.savefig(ROOT/'local_gaussian_probe_failures.png',dpi=180);plt.close(fig)


def main():
    results,decisions,plan=load();support,scores,probes,qualifications=tables(results,decisions,plan)
    for name,rows in [('support.csv',support),('predictive_scores.csv',scores),('local_gaussian_probes.csv',probes),('qualifications.csv',qualifications)]:csv_write(ROOT/name,rows)
    gain_figures(scores);qualification_figure(qualifications);probe_figure(probes)
    findings='''# Conditional RF predictive findings

All five frozen strict decisions are **inconclusive**. Positive raw density gains do not override unsupported transfers, failed optimization, or an unreliable local Gaussian approximation. The challenge panel and fixed identities/masks/aliases remain conditional development inputs.

- **DS26-0070:** joint gains change sign across time folds; target-family marginal gains favor SD1 in folds 0 and 2. Every SD4 time-fit fails the frozen local-Gaussian probe check; both receiver-transfer directions lack the required same-band independent-family calibration.
- **DS26-0309:** all three time-fold joint gains favor SD4 in both c arms, including other-family marginal predictions. Target-family marginals favor SD1 in folds 0 and 1. Both receiver-transfer directions have structural support, but RX1 transfer has optimizer failures. RX2 transfer qualifies and favors SD4. The complete five-partition rule remains inconclusive.
- **DS26-0040:** all time-fold joint gains favor SD4, while other-family marginal gains are slightly negative in fold 2. The target appears on only one receiver, preventing the reciprocal transfer test.
- **DS26-0044:** raw time-fold gains favor SD4, but some cells fail optimizer or local-Gaussian checks. Both transfer directions lack sufficient same-band calibration support.
- **FRSH-0004:** all three time folds in both c arms favor SD4 for joint and other-family marginal prediction, and all time-fit numerical checks pass. Reciprocal receiver transfer is unsupported because the target appears on only one receiver. These positive RF scores alone cannot establish localization benefit or a general model-selection rule.

Preprocessing uses a fixed 150 Hz engineering base, unit powers, training-only Gamma updates, and common regional-center/zero-reference starts. Predictive Gaussian noise matches the posterior inverse-precision moment. Shared nuisance and position covariance enter a joint normalized density, corrected for the regional box within the local Gaussian approximation. Gamma-mixture tails, residual short-time dependence, nonlinear posterior accuracy and inherited discovery selection remain limitations. The three marginal score subsets do not add, and overlapping randomized folds do not supply independent significance tests. No geography was read to make these figures.

[Joint gains](joint_gain_heatmap.png), [target and other-family gains](marginal_gain_heatmaps.png), [fit qualifications](qualification_grid.png), and [training probe failures](local_gaussian_probe_failures.png) display the raw evidence. Gray means unsupported transfer or an explicitly absent other-family held subset; × marks a failed four-fit paired numerical check, not a rejected satellite identity.

Compact tables retain [support](support.csv), [scores](predictive_scores.csv), [qualifications](qualifications.csv), and [individual training probes](local_gaussian_probes.csv). All numbers come from the sealed RF results and decisions. No optimizer, position-error calculation, or changed decision threshold is present in this presentation script.
'''
    (ROOT/'FINDINGS.md').write_text(findings)
    paths=[REPORT/'decisions.json',REPORT/'predictive/results.json',REPORT/'predictive/plan.json']
    manifest=dict(inputs_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths},
        outputs_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(ROOT.glob('*'))if p.is_file()and p.name!='manifest.json'},
        support_rows=len(support),paired_score_rows=len(scores),individual_fit_rows=len(qualifications),probe_rows=len(probes),geography_read=False,inference_run=False)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
