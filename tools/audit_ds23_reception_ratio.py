"""Check reception direction evidence against time trends and family permutations.

This diagnostic consumes frozen RF results only. It does not alter association
or localization and does not use geographic truth. Permutations preserve the
set of observed bands for each family and move both bands together.
"""

from collections import defaultdict
from pathlib import Path
import json
import math
import numpy as np


def held_family_loss(rows, direction=False, time=False):
    band=np.array([r['band'] for r in rows],int)
    family=np.array([r['norad'] for r in rows])
    y=np.array([r['log_ratio'] for r in rows])
    design=np.eye(2)[band]
    if time:
        t=np.array([r['median_time_s'] for r in rows])/300.-.5
        design=np.column_stack((design,t,t*t))
    if direction:design=np.column_stack((design,[r['feature'] for r in rows]))
    loss=0.;folds=0
    for f in sorted(set(family)):
        test=family==f;train=~test
        if any(np.sum(train & (band==b))<2 for b in set(band[test])):continue
        a=design[train];coef=np.linalg.solve(a.T@a+np.eye(a.shape[1])*.01,a.T@y[train])
        loss+=float(np.sum((y[test]-design[test]@coef)**2));folds+=1
    return dict(squared_error=loss,folds=folds)


def permuted_features(rows,rng):
    families=defaultdict(dict)
    for row in rows:families[row['norad']][row['band']]=row['feature']
    strata=defaultdict(list)
    for f,b in families.items():strata[tuple(sorted(b))].append(f)
    mapping={}
    for group in strata.values():mapping.update(zip(group,rng.permutation(group),strict=True))
    return [dict(r,feature=families[mapping[r['norad']]][r['band']]) for r in rows],sum(math.lgamma(len(g)+1) for g in strata.values())


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'reports/2026_10_21_ds23_reception_anchor_ratio/evaluation.json'
    document=json.loads(source.read_text());out=[];rng=np.random.default_rng(2026102103)
    for case in sorted(document['rows'],key=lambda r:r['case']):
        if case['status']!='complete' or 'held_family_SSE_fractional_improvement' not in case['validation']:continue
        rows=[]
        for r in case['family_band_medians']:
            times=[p['time_s'] for p in case['paired_points'] if p['norad']==r['norad'] and p['band']==r['band']]
            rows.append(dict(r,median_time_s=float(np.median(times))))
        baseline=held_family_loss(rows);beam=held_family_loss(rows,True)
        temporal=held_family_loss(rows,time=True);both=held_family_loss(rows,True,True)
        # Verify the independent calculation against the original full-family CV.
        assert abs(baseline['squared_error']-case['validation']['baseline_squared_error'])<1e-8
        assert abs(beam['squared_error']-case['validation']['direction_squared_error'])<1e-8
        observed=temporal['squared_error']-both['squared_error'];null=[]
        for _ in range(399):
            shuffled,log_count=permuted_features(rows,rng)
            null.append(temporal['squared_error']-held_family_loss(shuffled,True,True)['squared_error'])
        out.append(dict(case=case['case'],families=len({r['norad'] for r in rows}),
            originally_qualified=case['validation']['qualified'],band_only=baseline,direction=beam,time_only=temporal,time_and_direction=both,
            direction_gain_beyond_time=observed/max(temporal['squared_error'],1e-30),
            family_block_permutation_p=(1+sum(n>=observed for n in null))/400.,
            log_number_possible_family_permutations=log_count,permutations=399,
            conflicting_anchor_pairs=case['diagnostics'].get('conflicting_curved_family_anchors',0)))
    target=source.parent/'independent_control_audit.json'
    result=dict(rows=out,all_original_CV_scores_reproduced=True,
        tests_condition_on_existing_RF_associations_and_mode=True,
        time_only_control_is_quadratic_and_cannot_exclude_all_AGC_confounding=True,
        family_permutation_exchangeability_is_a_diagnostic_assumption=True,
        no_association_or_position_improvement_established=True,
        nominal_antenna_pattern_unmeasured=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    x=np.arange(len(out));colors=['#196a9b' if r['originally_qualified'] else '#999999' for r in out]
    axes[0].bar(x,[r['direction_gain_beyond_time']*100 for r in out],color=colors)
    axes[0].axhline(0,color='black',lw=.8);axes[0].set_ylabel('Held-family SSE reduction\nbeyond quadratic time (%)')
    axes[1].scatter(x,[r['family_block_permutation_p'] for r in out],c=colors)
    axes[1].axhline(.05,color='black',ls=':',label='0.05, unadjusted')
    axes[1].set_ylabel('Family-block permutation p');axes[1].set_ylim(0,1);axes[1].legend()
    axes[1].set_xticks(x,[r['case'].replace('DS23-','') for r in out],rotation=60)
    axes[1].set_xlabel('DS23 scan; blue = passed original reception-ratio check')
    fig.suptitle('Reception direction audit: conditional RF evidence, no position gain established')
    fig.tight_layout();fig.savefig(source.parent/'reception_direction_controls.png',dpi=150);plt.close(fig)
    print(json.dumps(dict(supported=len(out),positive_beyond_time=sum(r['direction_gain_beyond_time']>0 for r in out),
        unadjusted_p_le_05=sum(r['family_block_permutation_p']<=.05 for r in out),audit=str(target))))


if __name__=='__main__':main()
