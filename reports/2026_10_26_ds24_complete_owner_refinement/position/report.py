"""Saved-output RF reporting and separately released geographic evaluation."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024/family_cavity/position')
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c');METHODS=('original','corrected')
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def csv_write(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def verify(path):
    for name,digest in read(path)['files'].items():
        if sha(name)!=digest:raise ValueError('bound artifact changed: '+name)


def rf():
    verify(HERE/'RF_seal.json');out=HERE/'rf_report';out.mkdir(exist_ok=False);rows=[];summary=[]
    for case in CASES:
        result=read(HERE/case/'result.json');summary.append(result)
        for method in METHODS:
            for arm in ARMS:
                q=read(HERE/case/method/(arm+'_result.json'))
                row=dict(case=case,method=method,arm=arm,status=q['status'],operational_policy='original_reference')
                if q['status']=='complete':
                    raw=read(HERE/case/method/arm/'raw_endpoint.json');g=read(HERE/case/method/arm/'gates.json')
                    c=raw['likelihood_membership'];s=raw['summary']
                    row.update(east_km=q['endpoint_east_north_km'][0],north_km=q['endpoint_east_north_km'][1],
                        full_objective=q['full_objective'],curved_objective=s['curved_negative_twice_elbo'],
                        predictive_objective=raw['predictive_objective'],conditional_RMS_hz=q['conditional_RMS_hz'],
                        original_single_arm_valid=q['original_single_arm_valid'],Gamma_converged=q['Gamma_converged'],
                        final_log_precision_change=raw['final_log_precision_change'],final_phase_change_s=q['final_phase_change_s'],
                        maximum_unclipped_phase_s=g['maximum_unclipped_phase_s'],
                        curved_likelihood_IDs=c['curved_count'],predictive_likelihood_IDs=c['predictive_count'],
                        original_accepted_IDs_lost=q['postfit_IDs_lost'],
                        associated_IDs=g['membership']['associated'],postfit_only_IDs=len(g['membership']['postfit_only_observation_ids']),
                        failed_curved_tracks=sum(not t['compatible'] for t in s['gates']['tracks']),
                        failed_predictive_tracks=sum(not t['compatible'] for t in s['linear_gates']),
                        original_reproduction_pass=q['baseline_reproduction']['passed'] if q['baseline_reproduction'] else None,
                        research_paired_qualified=result['corrected_research_paired_qualified'],seconds=q['seconds'])
                rows.append(row)
    csv_write(out/'outcomes.csv',rows);contrasts=[]
    for case in CASES:
        for arm in ARMS:
            rr={r['method']:r for r in rows if r['case']==case and r['arm']==arm}
            if any(x['status']!='complete' for x in rr.values()):continue
            a,b=rr['original'],rr['corrected'];delta=np.array([b['east_km']-a['east_km'],b['north_km']-a['north_km']])
            pa=read(HERE/case/'original'/arm/'raw_endpoint.json');pb=read(HERE/case/'corrected'/arm/'raw_endpoint.json')
            precision_a=np.array(pa['noise_precision']);precision_b=np.array(pb['noise_precision']);use=precision_a>0
            contrasts.append(dict(case=case,arm=arm,movement_east_north_km=delta.tolist(),movement_m=float(np.linalg.norm(delta)*1000),
                objective_difference=b['full_objective']-a['full_objective'],conditional_RMS_difference_hz=b['conditional_RMS_hz']-a['conditional_RMS_hz'],
                median_Gamma_precision_ratio=float(np.median(precision_b[use]/precision_a[use])),
                minimum_Gamma_precision_ratio=float(np.min(precision_b[use]/precision_a[use])),
                maximum_Gamma_precision_ratio=float(np.max(precision_b[use]/precision_a[use]))))
    write(out/'summary.json',dict(rows=rows,contrasts=contrasts,all8_slots=True,
        cumulative_worker_seconds=read(HERE/'execution.json')['cumulative_worker_seconds'],
        objective_changes_are_different_observed_data_not_model_Bayes_factors=True,
        operational_policy='original_reference',GPS_read=False))
    files=[Path(__file__),HERE/'RF_seal.json',out/'outcomes.csv',out/'summary.json']
    write(out/'seal.json',dict(files={str(p):sha(p) for p in files}))
    print(json.dumps(contrasts,indent=2))


def latlon(point):
    return 37.906+point[1]/111.,-122.545+point[0]/(111.32*math.cos(math.radians(37.906)))


def distance(a,b):
    la,lo,lb,lp=map(math.radians,(*a,*b));h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def freeze_evaluation():
    write(HERE/'evaluation_freeze.json',dict(files={str(Path(__file__)):sha(__file__)},geographic_data_read=False))


def geography(reference):
    verify(HERE/'evaluation_freeze.json');verify(HERE/'RF_seal.json');verify(HERE/'rf_report/seal.json')
    audit=read(ROOT/'audit/position_terminal.json')
    if not audit['all_passed'] or not audit.get('RF_ready_for_separate_geographic_evaluation') or audit['RF_seal_sha256']!=sha(HERE/'RF_seal.json'):
        raise ValueError('exact passing terminal audit required')
    out=HERE/'geographic';out.mkdir(exist_ok=False);rows=[]
    rf_rows=read(HERE/'rf_report/summary.json')['rows']
    for row in rf_rows:
        saved=read(SOURCE/(row['case']+'.json'))['policy_arms'][row['arm']]
        baseline=distance(latlon(saved['endpoint_east_north_km']),reference)
        raw=distance(latlon([row['east_km'],row['north_km']]),reference) if row['status']=='complete' else None
        rows.append(dict(row,raw_position_error_km=raw,original_reference_error_km=baseline,
            raw_error_minus_reference_m=1000*(raw-baseline) if raw is not None else None,
            operational_policy_error_km=baseline,operational_policy='exact_original_reference'))
    csv_write(out/'outcomes.csv',rows);paired=[]
    for case in CASES:
        for arm in ARMS:
            rr={r['method']:r for r in rows if r['case']==case and r['arm']==arm};a,b=rr['original'],rr['corrected']
            paired.append(dict(case=case,arm=arm,original_error_km=a['raw_position_error_km'],corrected_error_km=b['raw_position_error_km'],
                raw_gain_m=1000*(a['raw_position_error_km']-b['raw_position_error_km']) if a['raw_position_error_km'] is not None and b['raw_position_error_km'] is not None else None,
                corrected_research_paired_qualified=b.get('research_paired_qualified',False),operational_error_km=a['operational_policy_error_km']))
    write(out/'summary.json',dict(rows=rows,paired=paired,reference_latlon=reference,slots=8,new_fits=0,
        root_release='explicit coordinator message following passing RF audit',operational_policy='exact_original_reference'))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(10.8,4.7),sharey=True,layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for i,case in enumerate(CASES):
            pair=next(x for x in paired if x['case']==case and x['arm']==arm)
            for method,offset,color in (('original',-.17,'.5'),('corrected',.17,'#176b8b')):
                error=pair[method+'_error_km']
                if error is None:ax.text(i+offset,0,'Missing',rotation=90,ha='center',va='bottom');continue
                ax.bar(i+offset,error,width=.32,color=color,label=method if i==0 else None)
                ax.text(i+offset,error,f'{error:.3f}',ha='center',va='bottom',fontsize=9)
            ax.plot([i-.38,i+.38],[pair['operational_error_km']]*2,'--',color='#a34421',lw=1.2)
        ax.set_xticks(range(2),CASES);ax.set_title('c = 0' if arm=='c0' else 'Fitted c');ax.grid(axis='y',alpha=.2)
        ymax=max((r['raw_position_error_km'] or 0) for r in rows)
        ax.set_ylim(0,max(ymax*1.2,.1));ax.set_ylabel('Position error (km)');ax.legend()
    fig.suptitle('Matched original versus complete-owner CFO refinement\nRaw diagnostic endpoints; dashed lines are unchanged operational references',fontsize=12)
    fig.savefig(out/'paired_position_errors.png',dpi=180);plt.close(fig)
    files=[p for p in out.iterdir() if p.is_file()]+[Path(__file__),HERE/'RF_seal.json',HERE/'evaluation_freeze.json',ROOT/'audit/position_terminal.json']
    write(out/'seal.json',dict(files={str(p):sha(p) for p in files}));print(json.dumps(paired,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('rf','freeze_evaluation','geography'))
    parser.add_argument('--reference-latlon',nargs=2,type=float);args=parser.parse_args()
    if args.action=='geography':
        if args.reference_latlon is None:parser.error('explicit released evaluation reference required')
        geography(args.reference_latlon)
    else:{'rf':rf,'freeze_evaluation':freeze_evaluation}[args.action]()
