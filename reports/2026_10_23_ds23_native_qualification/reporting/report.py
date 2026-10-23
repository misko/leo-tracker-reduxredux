"""Reporting-only assembled410 evaluation; GPS cannot enter the RF runner."""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import statistics
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
FROZEN=Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023')
HELPER=FROZEN/'source/report_full.py'
spec=importlib.util.spec_from_file_location('frozen_reporting_helper',HELPER)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
ARMS=('c0','fitted_c')
METHODS=('reference','prior_ordinary','disable_rescue','one_pass')
TERMINAL={'accepted','unchanged_control','graph_fallback_no_new_path_failure','graph_fallback_no_new_paths_left','graph_fallback_refit_rejected'}

def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(protocol,new):
    expected=set(protocol['eligible_cases']+protocol['controls'])
    assert len(expected)==32 and len(protocol['eligible_cases'])==29
    if set(new)!=expected:raise ValueError('incomplete32-case execution')
    for case,d in new.items():
        if d.get('status') not in TERMINAL:raise ValueError(f'nonterminal or execution failure: {case}/{d.get("status")}')
        if bool(d.get('candidate_accepted'))!=(d['status']=='accepted'):raise ValueError('acceptance status disagreement')
        if bool(d.get('original_rescue_eligible'))!=(case in protocol['eligible_cases']):raise ValueError('frozen eligibility mismatch')

def views(case,frozen,new,eligible):
    return dict(reference=frozen['reference'],prior_ordinary=frozen['final'],
        disable_rescue=new['disable_rescue_final'] if eligible else frozen['final'],
        one_pass=new['policy_final'] if eligible else frozen['final'])

def build(protocol,frozen,new,formats):
    validate(protocol,new);rows=[]
    for case in protocol['available']:
        eligible=case in protocol['eligible_cases']
        for method,view in views(case,frozen[case],new.get(case),eligible).items():
            for arm in ARMS:
                fit=view['arms'][arm];n,total=helper.coverage(view['coverage'][arm])
                rows.append(dict(case=case,cohort=formats[case],eligible=eligible,method=method,arm=arm,
                    source_status=new[case]['status'] if eligible and method in ('one_pass','disable_rescue') else frozen[case]['status'],
                    error_km=helper.position_error(fit['endpoint_latlon']),RMS_hz=fit.get('RMS_hz'),
                    associated_unique=n,total_GLRT=total,associated_percent=100*n/total))
    return rows

def summarize(rows):
    summaries=[];pairs=[];index={(r['case'],r['method'],r['arm']):r for r in rows}
    for r in rows:
        if r['method'] not in ('one_pass','disable_rescue'):continue
        baselines=('reference','prior_ordinary','disable_rescue') if r['method']=='one_pass' else ('reference','prior_ordinary')
        for baseline in baselines:
            b=index[r['case'],baseline,r['arm']]
            pairs.append(dict(case=r['case'],cohort=r['cohort'],eligible=r['eligible'],method=r['method'],arm=r['arm'],baseline=baseline,
                baseline_error_km=b['error_km'],error_km=r['error_km'],delta_error_km=r['error_km']-b['error_km'],
                delta_coverage_IDs=r['associated_unique']-b['associated_unique'],
                delta_RMS_hz=r['RMS_hz']-b['RMS_hz'] if r['RMS_hz'] is not None and b['RMS_hz'] is not None else None))
    for population in ('assembled410','eligible29'):
        for cohort in ('all','fast','adaptive'):
            rr=[r for r in rows if (population=='assembled410' or r['eligible']) and (cohort=='all' or r['cohort']==cohort)]
            for method in METHODS:
                for arm in ARMS:
                    vv=[r for r in rr if r['method']==method and r['arm']==arm];errors=[r['error_km'] for r in vv]
                    n=sum(r['associated_unique'] for r in vv);total=sum(r['total_GLRT'] for r in vv)
                    s=dict(population=population,cohort=cohort,method=method,arm=arm,scans=len(vv),mean_km=statistics.mean(errors) if errors else None,
                        median_km=statistics.median(errors) if errors else None,p95_km=helper.quantile(errors,.95) if errors else None,worst_km=max(errors) if errors else None,
                        associated_unique_summed=n,total_GLRT=total,coverage_percent=100*n/total if total else None)
                    summaries.append(s)
    regressions=[]
    for population in ('assembled410','eligible29'):
        for cohort in ('all','fast','adaptive'):
            for method in ('one_pass','disable_rescue'):
                for baseline in ('reference','prior_ordinary','disable_rescue'):
                    for arm in ARMS:
                        pp=[p for p in pairs if p['method']==method and p['baseline']==baseline and p['arm']==arm and (population=='assembled410' or p['eligible']) and (cohort=='all' or p['cohort']==cohort)]
                        if not pp:continue
                        regressions.append(dict(population=population,cohort=cohort,method=method,baseline=baseline,arm=arm,scans=len(pp),
                            mean_delta_error_km=statistics.mean(p['delta_error_km'] for p in pp),regressions_above_half_km=sum(p['delta_error_km']>.5 for p in pp),regressions_above_1km=sum(p['delta_error_km']>1 for p in pp),
                            improvements_above_half_km=sum(p['delta_error_km']<-.5 for p in pp),coverage_delta_IDs=sum(p['delta_coverage_IDs'] for p in pp)))
    return summaries,pairs,regressions

def table(name,rows):
    path=ROOT/'tables'/(name+'.csv');path.parent.mkdir(exist_ok=True)
    if not rows:path.write_text('');return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');writer.writeheader();writer.writerows(rows)

def plots(rows,pairs,new,eligible):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    out=ROOT/'figures';out.mkdir(exist_ok=True)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,arm in enumerate(ARMS):
        for method in METHODS:
            v=sorted(r['error_km'] for r in rows if r['arm']==arm and r['method']==method)
            axes[0,col].plot(v,np.arange(1,len(v)+1)/len(v),label=method)
        axes[0,col].set(title=arm+' · assembled410',xlabel='Position error(km)',ylabel='CDF');axes[0,col].legend(fontsize=8)
        for baseline in ('reference','prior_ordinary','disable_rescue'):
            v=sorted(p['delta_error_km'] for p in pairs if p['method']=='one_pass' and p['arm']==arm and p['baseline']==baseline)
            axes[1,col].plot(v,np.arange(1,len(v)+1)/len(v),label=baseline)
        axes[1,col].axvline(0,color='black',lw=.7);axes[1,col].set(xlabel='One-pass minus baseline position error(km)',ylabel='Paired-change CDF');axes[1,col].legend(fontsize=8)
    fig.suptitle('Fixed reuse of410 frozen recordings;29 eligible cases reconsidered,3 unchanged controls')
    fig.savefig(out/'assembled410_cdf_pairs.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,12),layout='constrained')
    for col,arm in enumerate(ARMS):
        pp=[next(p for p in pairs if p['case']==case and p['arm']==arm and p['method']=='one_pass' and p['baseline']=='disable_rescue') for case in eligible]
        colors=['#1b9e77' if new[c]['status']=='accepted' else '#888888' for c in eligible]
        for row,key in [(0,'delta_error_km'),(1,'delta_coverage_IDs')]:
            axes[row,col].barh(range(len(pp)),[p[key] for p in pp],color=colors)
            axes[row,col].set_yticks(range(len(pp)),eligible,fontsize=7);axes[row,col].axvline(0,c='black',lw=.7)
            axes[row,col].set(title=arm,xlabel='One-pass minus disable: '+('error(km)' if row==0 else 'unique original IDs'))
    fig.suptitle('29 RF-eligible outcomes · green accepted; gray graph fallback · accuracy and coverage separate')
    fig.savefig(out/'eligible29_outcomes.png',dpi=160);plt.close(fig)

def main():
    protocol=read(ROOT/'protocol.json');hashes={};frozen={};new={}
    paths=[ROOT/'protocol.json',HELPER,FROZEN/'tables/positions.csv',Path(__file__),ROOT/'reporting/test_report.py']
    for case in protocol['available']:
        p=FROZEN/'raw'/case/'result.json';frozen[case]=read(p);paths.append(p)
    for case in protocol['eligible_cases']+protocol['controls']:
        p=ROOT/'raw'/case/'result.json'
        if p.exists():new[case]=read(p);paths.append(p)
    validate(protocol,new)
    formats={r['case']:r['cohort'] for r in csv.DictReader((FROZEN/'tables/positions.csv').open())}
    rows=build(protocol,frozen,new,formats);summaries,pairs,regressions=summarize(rows)
    assert len(rows)==410*4*2
    assert all(s['total_GLRT']==1036559 for s in summaries if s['population']=='assembled410' and s['cohort']=='all')
    outcomes=[];exclusions=[];losses=[]
    for case,d in new.items():
        outcomes.append(dict(case=case,cohort=formats[case],eligible=case in protocol['eligible_cases'],status=d['status'],accepted=d['status']=='accepted',attempted_refit=d['attempted_refit'],
            seconds=d['seconds'],new_paths=d.get('original_new_paths'),new_points=d.get('original_new_points'),excluded_paths=len(d.get('excluded_keys',[])),excluded_points=d.get('excluded_new_points'),
            remaining_new_points=d.get('original_new_points',0)-d.get('excluded_new_points',0),paired_gates_pass=d.get('paired_gates_pass'),parent_IDs_preserved=d.get('original_parent_IDs_preserved'),reason=d.get('reason')))
        for component,reasons in d.get('RF_exclusion_reasons',{}).items():
            for gate,slack in reasons.items():exclusions.append(dict(case=case,component=component,gate=gate,slack=slack,evidence='excluded_new_whole_path'))
        for gate,slack in d.get('failures_on_protected_evidence',{}).items():exclusions.append(dict(case=case,component=None,gate=gate,slack=slack,evidence='protected_not_excluded'))
        for arm,score in d.get('common_full_mask_scores',{}).items():
            before=d['original_primary_arms'][arm]['negative_twice_elbo']
            losses.append(dict(case=case,arm=arm,status=d['status'],mask='identical original full primary evidence; diagnostic only',original_primary_objective=before,
                reduced_fit_endpoint_on_full_mask_objective=score['objective'],delta_full_mask_objective=score['objective']-before,
                negative_full_mask_gates=sum(v<0 for v in score['gate_slacks'].values())))
    ablation=[];index={(r['case'],r['method'],r['arm']):r for r in rows}
    for r in rows:
        if r['arm']=='c0':
            f=index[r['case'],r['method'],'fitted_c'];ablation.append(dict(case=r['case'],cohort=r['cohort'],eligible=r['eligible'],method=r['method'],fitted_minus_c0_error_km=f['error_km']-r['error_km'],fitted_minus_c0_RMS_hz=f['RMS_hz']-r['RMS_hz'] if f['RMS_hz'] is not None and r['RMS_hz'] is not None else None))
    for name,data in [('per_scan',rows),('summary',summaries),('paired_changes',pairs),('regressions',regressions),('case_outcomes',outcomes),('exclusions_gate_causes',exclusions),('runtime',outcomes),('common_full_mask_losses',losses),('c_ablation',ablation)]:table(name,data)
    runtime=[]
    for scope in ('all32','eligible29','controls3'):
        selected=[r for r in outcomes if scope=='all32' or r['eligible']==(scope=='eligible29')]
        times=[r['seconds'] for r in selected]
        runtime.append(dict(scope=scope,cases=len(times),summed_worker_seconds=sum(times),mean_seconds=statistics.mean(times),median_seconds=statistics.median(times),maximum_seconds=max(times),
            attempted_refits=sum(r['attempted_refit'] for r in selected),accepted=sum(r['accepted'] for r in selected)))
    table('runtime_summary',runtime)
    table('outcome_counts',[dict(status=status,cases=n) for status,n in sorted(Counter(d['status'] for d in new.values()).items())])
    plots(rows,pairs,new,protocol['eligible_cases'])
    receipt=dict(status='complete_nonprovisional_execution',GPS_reporting_only=True,assembled_scans=410,new_inspections=32,eligible_cases=29,unchanged_controls=3,
        new_accepted=sum(d['status']=='accepted' for d in new.values()),execution_failures=0,full_coverage_denominator=1036559,
        interpretation='410 assembled fixed-reuse comparisons, not410 new fits; changed-mask raw losses never compared; common-full-mask endpoint scores diagnostic only; c frequency fit and position accuracy separate',
        input_sha256={str(p):digest(p) for p in paths},runtime=runtime,summary=summaries,regressions=regressions)
    (ROOT/'reporting/receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('input_sha256','summary','regressions')}))

if __name__=='__main__':main()
