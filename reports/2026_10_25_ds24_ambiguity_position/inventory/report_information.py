"""Saved-output-only cohort information report; no geometry or scientific solve."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
ARMS=('c0','fitted_c')

def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def csvwrite(p,rows):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def weak_sd(q,a,augmented=True):
    z=q.get('arms',{}).get(a,{})
    key='augmented_baseline_weak_variance_km2' if augmented else 'baseline_weak_variance_km2'
    return float(np.sqrt(z[key])) if z.get('status')=='complete' else None

def main():
    seal=read(HERE/'RF_seal.json')
    assert all(sha(Path(p))==h for p,h in seal['files'].items())
    result=read(HERE/'results.json');inv=read(HERE/'inventory.json');rows=result['rows'];out=HERE/'report';out.mkdir()
    owner=[];ranks=[];summaries=[]
    for q in rows:
        owner.append(dict(case=q['case'],component=q['component'],receiver=q['receiver'],channel=q['channel'],points=q['points'],span_s=q['span_s'],rf_hz=q['rf_hz'],native_ID_order_sha256=hashlib.sha256(json.dumps(q['observation_ids'],separators=(',',':')).encode()).hexdigest(),row_index=q['row_index'],candidate_norad=q['candidate_norad'],alias=q['alias'],original_curvature=q['archived_original_active_curvature'],archived_compatible=q['archived_nomination_compatible'],quality_status=q['quality_status'],family_active=q['family_has_parent_likelihood'],family_has_mode_slots=q.get('family_has_parent_physical_modes'),eligible=q['eligible'],status=q['status'],accepted_overlap_c0=len(q['accepted_ID_overlap']['c0']) if q['accepted_ID_overlap'] else None,accepted_overlap_fitted_c=len(q['accepted_ID_overlap']['fitted_c']) if q['accepted_ID_overlap'] else None,postfit_only_overlap_c0=len(q['postfit_only_ID_overlap']['c0']) if q['postfit_only_ID_overlap'] else None,postfit_only_overlap_fitted_c=len(q['postfit_only_ID_overlap']['fitted_c']) if q['postfit_only_ID_overlap'] else None,prior_covered=len(q['prior_source_specific_work'])>0,excluded_case=q['case_excluded_from_new_choice'],exclusions='; '.join(q['exclusion_reasons'])))
        if not q['eligible']:continue
        z=dict(case=q['case'],component=q['component'],candidate_norad=q['candidate_norad'],points=q['points'],span_s=q['span_s'],status=q['status'],prior_covered=len(q['prior_source_specific_work'])>0,count_rank=q.get('count_rank'),duration_rank=q.get('duration_rank'),information_rank=q.get('information_rank'),unexhausted_count_rank=q.get('unexhausted_count_rank'),unexhausted_duration_rank=q.get('unexhausted_duration_rank'),unexhausted_information_rank=q.get('unexhausted_information_rank'),paired_variance_reduction=q.get('paired_ranking_score'),mode_block=q.get('incumbent_mode_block'),case_excluded=q['case_excluded_from_new_choice'])
        for a in ARMS:
            v=q.get('arms',{}).get(a,{})
            z.update({a+'_variance_reduction':v.get('fractional_weak_variance_reduction'),a+'_baseline_weak_SD_km':weak_sd(q,a,False),a+'_augmented_weak_SD_km':weak_sd(q,a),a+'_error':v.get('error',q.get('error'))})
        ranks.append(z)
    for c in inv['cases']:
        case=c['case'];r=[q for q in rows if q['case']==case];e=[q for q in r if q['eligible']];done=[q for q in e if q['status']=='complete'];new=[q for q in done if q['unexhausted_within_declared_audit'] and case not in [f'DS24-{i:04d}' for i in range(10,14)]]
        summaries.append(dict(case=case,native_owners=len(r),original_curved_owners=sum(q['archived_original_active_curvature'] for q in r),eligible_owners=len(e),complete_information=len(done),blocked=sum(q['status']=='blocked' for q in e),unavailable=sum(q['status']=='unavailable' for q in e),scoped_remaining_complete=len(new),remaining_material=sum(q['paired_ranking_score']>=.05 for q in new),reused_old_four=case in [f'DS24-{i:04d}' for i in range(10,14)],new_nominee=next((q['component'] for q in result['selection'] if q['case']==case),None)))
    csvwrite(out/'all_owners.csv',owner);csvwrite(out/'information_ranks.csv',ranks);csvwrite(out/'case_summary.csv',summaries)
    selected=[]
    for pick in result['selection']:
        q=next(z for z in rows if z['case']==pick['case'] and z['component']==pick['component'])
        v=dict(pick,points=q['points'],span_s=q['span_s'],family_active=q['family_has_parent_likelihood'])
        for a in ARMS:v.update({a+'_variance_reduction':q['arms'][a]['fractional_weak_variance_reduction'],a+'_baseline_weak_SD_km':weak_sd(q,a,False),a+'_augmented_weak_SD_km':weak_sd(q,a)})
        selected.append(v)
    if selected:csvwrite(out/'selection.csv',selected)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=[c['case'] for c in inv['cases']];xx=np.arange(len(cases))
    fig,axes=plt.subplots(2,1,figsize=(13,8),layout='constrained')
    a=np.array([c['original_curved_owners'] for c in summaries]);b=np.array([c['eligible_owners'] for c in summaries])
    axes[0].bar(xx,a-b,color='#b7c1c8',label='Excluded by existing ownership');axes[0].bar(xx,b,bottom=a-b,color='#277a9c',label='Complete eligible owner')
    axes[0].set(ylabel='Original curved owners',title='Ownership screening leaves complete sources for conditional design checks');axes[0].legend(fontsize=9)
    for k,case in enumerate(cases):
        pool=[q for q in rows if q['case']==case and q['eligible']]
        for n,q in enumerate(pool):
            if q['status']=='complete':axes[1].plot(k+(n-(len(pool)-1)/2)*.06,100*q['paired_ranking_score'],'o',ms=4,color='#a4a4a4' if q['case_excluded_from_new_choice'] or q['prior_source_specific_work'] else '#277a9c',alpha=.7)
            else:axes[1].plot(k,0,'x',ms=7,color='#b34c37')
        pick=next((q for q in selected if q['case']==case),None)
        if pick:axes[1].plot(k,100*pick['paired_ranking_score'],'*',ms=15,color='#d17c19',mec='black',mew=.4)
    axes[1].axhline(5,color='black',ls='--',lw=1,label='Frozen 5% both-arm variance threshold')
    axes[1].set(ylabel='Minimum c-arm weak variance reduction (%)',title='Local Gaussian design gains, conditional on each archived identity')
    axes[1].legend(fontsize=9);axes[1].grid(alpha=.15)
    for ax in axes:ax.set_xticks(xx,[c[-4:] for c in cases],rotation=60)
    fig.suptitle('All 24 scans are exposed development data; stars allocate follow-up, not accepted identities')
    for ext in ('png','pdf'):fig.savefig(out/f'cohort_applicability.{ext}',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,a in zip(axes,ARMS):
        for i,sel in enumerate(selected):
            pool=[q for q in rows if q['case']==sel['case'] and q['eligible'] and q['unexhausted_within_declared_audit']]
            info=next(q for q in pool if q['component']==sel['component'])
            controls=[('baseline',None),('count',next(q for q in pool if q['unexhausted_count_rank']==1)),('duration',next(q for q in pool if q['unexhausted_duration_rank']==1)),('information',info)]
            for j,(name,q) in enumerate(controls):
                sd=weak_sd(info,a,False) if q is None else weak_sd(q,a)
                if sd is not None:ax.bar(i+(j-1.5)*.18,sd,width=.17,color=['#b7c1c8','#78a6c3','#a3b381','#d17c19'][j],label=name if i==0 else None)
                else:ax.text(i+(j-1.5)*.18,0,'blocked',rotation=90,ha='center',va='bottom',fontsize=7)
        ax.set_xticks(range(len(selected)),[q['case'][-4:] for q in selected]);ax.set(title=a,ylabel='Baseline-axis local weak SD (km)');ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Information versus length on the identical scoped remaining-owner pool\nFrozen local Gaussian mean design; uncertainty is not calibrated geographic error')
    for ext in ('png','pdf'):fig.savefig(out/f'length_vs_information.{ext}',dpi=160)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,4.8),layout='constrained')
    count=np.array([q['scoped_remaining_complete'] for q in summaries]);material=np.array([q['remaining_material'] for q in summaries])
    ax.bar(xx,count-material,color='#b7c1c8',label='Below 5% both-arm threshold');ax.bar(xx,material,bottom=count-material,color='#277a9c',label='At least 5% in both arms')
    ax.set_xticks(xx,[c[-4:] for c in cases],rotation=60);ax.set(ylabel='Complete scoped remaining owners',title='Scope is remaining work in audited ledgers, not previously unseen evidence');ax.legend(fontsize=9)
    for ext in ('png','pdf'):fig.savefig(out/f'remaining_support.{ext}',dpi=160)
    plt.close(fig)
    summary=dict(case_summary=summaries,selection=selected,owner_count=len(rows),eligible_owners=len(ranks),complete_owners=sum(q['status']=='complete' for q in ranks),blocked_owners=sum(q['status']=='blocked' for q in ranks),unavailable_owners=sum(q['status']=='unavailable' for q in ranks),remaining_material_owners=sum(q['remaining_material'] for q in summaries),case_failures=result['case_failures'],cumulative_worker_seconds=result['cumulative_worker_seconds'],new_position_fits=0,identity_qualification=False,GPS_or_errors_used=False,large_local_results_and_external_inputs_required=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    large=[HERE/'metadata.json',HERE/'inventory.json',HERE/'results.json']+sorted((HERE/'ownership').rglob('*.json'))+sorted((HERE/'arrays').glob('*.npz'))
    (out/'local_artifacts.json').write_text(json.dumps(dict(files=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in large],purpose='Local evidence inventory; these arrays/ledgers are not all duplicated into the lean Git report.'),indent=2)+'\n')
    files=[Path(__file__)]+[p for p in out.iterdir() if p.is_file()]
    (out/'seal.json').write_text(json.dumps(dict(files={str(p):sha(p) for p in files},RF_seal_sha256=sha(HERE/'RF_seal.json')),indent=2)+'\n')

if __name__=='__main__':main()
