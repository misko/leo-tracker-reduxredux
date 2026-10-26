"""Read sealed diagnostics and evaluate matched-position endpoints only."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'report'
CASES=('DS24-0010','DS24-0011','DS24-0012','DS24-0013')
ARMS=('c0','fitted_c')

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')
def csvout(p,rows):
    with p.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def check(mapping):
    for path,digest in mapping.items():assert sha(path)==digest,path
def error(point,reference):
    lat=37.906+point[1]/111;lon=-122.545+point[0]/(111.32*math.cos(math.radians(37.906)))
    a,b,c,d=map(math.radians,(lat,lon,*reference))
    v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,max(0,v))))


def main(reference):
    for branch in ('matched','residual'):
        check(load(ROOT/branch/'RF_seal.json')['files'])
        check(load(ROOT/branch/'protocol.json')['sources'])
    check({p:v['sha256'] for p,v in load(ROOT/'supplemental_provenance.json')['files'].items()})
    audit=load(ROOT/'prediction_audit/summary.json')
    assert audit['all_complete'] and audit['exact_vectors']==96
    OUT.mkdir(exist_ok=True)
    rows=[r for rr in load(ROOT/'matched/execution.json')['results'] for r in rr]
    assert len(rows)==96 and all(r['status']=='complete' for r in rows)
    matched=[]
    for r in rows:
        matched.append(dict(case=r['case'],arm=r['arm'],method=r['method'],points=r['points'],
            error_km=error(r['endpoint_east_north_km'],reference),frequency_RMS_hz=r['frequency_RMS_hz'],
            phase_checks_pass=r['phase_checks_pass'],final_solver_stop=r['history'][-1]['fit']['stopped'],
            any_iteration_budget=any(h['fit']['stopped']=='iteration_budget' for h in r['history']),
            final_phase_change_s=r['final_phase_change_s']))
    comparisons=[]
    for case in CASES:
        for arm in ARMS:
            rr={r['method']:r for r in matched if r['case']==case and r['arm']==arm}
            for kind,lo,hi in [('unmatched',[rr['low']],[rr['high']]),
                ('count_only',[rr[f'count_low_{i}'] for i in range(3)],[rr['high']]),
                ('family_RX_time',[rr[f'matched_low_{i}'] for i in range(3)],[rr[f'matched_high_{i}'] for i in range(3)])]:
                comparisons.append(dict(case=case,arm=arm,comparison=kind,
                    low_points=lo[0]['points'],high_points=hi[0]['points'],
                    low_error_mean_km=float(np.mean([r['error_km'] for r in lo])),
                    high_error_mean_km=float(np.mean([r['error_km'] for r in hi])),
                    low_error_min_km=min(r['error_km'] for r in lo),low_error_max_km=max(r['error_km'] for r in lo),
                    high_error_min_km=min(r['error_km'] for r in hi),high_error_max_km=max(r['error_km'] for r in hi),
                    high_minus_low_km=float(np.mean([r['error_km'] for r in hi])-np.mean([r['error_km'] for r in lo]))))
    residual=[];witness=[];all_training_checks=True
    source={}
    for path in sorted((ROOT/'residual/results').glob('*.json')):
        a=load(path);assert a['status']=='complete';source[(a['case'],a['mask'])]=a
        for arm,b in a['arms'].items():
            crossover=b['crossover'];score=lambda model,endpoint,group='all':crossover[model][endpoint]['scores'][group]['negative_twice_log_density']
            checks=all(f['final_phase_change_s']<=.01 and f['training_final_log_precision_change']<=1.0001e-5
                and f['maximum_unclipped_phase_s']<=15.000001 and
                all(x['fit']['stopped']!='iteration_budget' for x in f['history']) for f in b['fits'].values())
            all_training_checks &= checks
            for group in crossover['baseline']['baseline']['scores']:
                residual.append(dict(case=a['case'],mask=a['mask'],arm=arm,group=group,norad=a['selected']['norad'],
                    held_points=crossover['baseline']['baseline']['scores'][group]['dimensions'],
                    own_model_gain=score('baseline','baseline',group)-score('sharedRF50','sharedRF50',group),
                    movement_gain_baseline_predictor=score('baseline','baseline',group)-score('baseline','sharedRF50',group),
                    movement_gain_shared_predictor=score('sharedRF50','baseline',group)-score('sharedRF50','sharedRF50',group),
                    training_checks_pass=checks))
    for case in CASES:
        for arm in ARMS:
            for rx in ('RX1','RX2'):
                whole=source[(case,'whole')]['arms'][arm]['crossover']['baseline']['baseline']
                partial=source[(case,rx)]['arms'][arm]['crossover']['baseline']['baseline']
                aa=np.load(whole['arrays']);bb=np.load(partial['arrays']);select=aa['receiver']==int(rx[-1])
                assert set(aa['ids'][select])==set(bb['ids'])
                witness.append(dict(case=case,arm=arm,target_receiver=rx,
                    norad=source[(case,'whole')]['selected']['norad'],points=int(select.sum()),
                    gain_from_other_receiver_family=whole['scores'][rx]['negative_twice_log_density']-
                        partial['scores']['all']['negative_twice_log_density'],
                    training_position_refitted=True,identical_test_IDs=True))
    primary=[r for r in residual if r['mask']=='whole' and r['group']=='all']
    arm_summary={}
    for arm in ARMS:
        rr=[r for r in primary if r['arm']==arm]
        arm_summary[arm]=dict(own_model_total_gain=sum(r['own_model_gain'] for r in rr),
            all_cases_own_model_positive=all(r['own_model_gain']>0 for r in rr),
            movement_total_baseline_predictor=sum(r['movement_gain_baseline_predictor'] for r in rr),
            movement_total_shared_predictor=sum(r['movement_gain_shared_predictor'] for r in rr))
    advance=all_training_checks and audit['all_checks_pass'] and all(v['all_cases_own_model_positive'] and
        v['own_model_total_gain']>=10 and v['movement_total_baseline_predictor']>0 and v['movement_total_shared_predictor']>0
        for v in arm_summary.values())
    totals={arm:{kind:{'low_mean_km':float(np.mean([r['low_error_mean_km'] for r in comparisons if r['arm']==arm and r['comparison']==kind])),
        'high_mean_km':float(np.mean([r['high_error_mean_km'] for r in comparisons if r['arm']==arm and r['comparison']==kind]))}
        for kind in ('unmatched','count_only','family_RX_time')} for arm in ARMS}
    value=dict(matched_rows=matched,matched_comparisons=comparisons,matched_four_case_means=totals,
        residual_comparisons=residual,other_receiver_witness=witness,primary_receiver_summary=arm_summary,
        all_residual_training_checks_pass=all_training_checks,all_crossed_score_checks_pass=audit['all_checks_pass'],
        receiver_correction_advances=bool(advance),reference_latlon=reference,
        GPS_evaluation_only=True,fixed_assignments=True,independent_validation=False,
        matched_precision_inherited_from_full_data=True,no_operational_change=True)
    write(OUT/'summary.json',value)
    csvout(OUT/'matched_endpoints.csv',matched);csvout(OUT/'matched_comparisons.csv',comparisons)
    csvout(OUT/'residual_comparisons.csv',residual);csvout(OUT/'other_receiver_witness.csv',witness)
    figures(value)
    write(OUT/'seal.json',dict(files={str(p):sha(p) for p in OUT.iterdir() if p.is_file()},source_sha256=sha(__file__)))
    print(json.dumps({k:value[k] for k in ('matched_four_case_means','primary_receiver_summary','receiver_correction_advances','all_crossed_score_checks_pass')},indent=2))


def save(fig,name):
    for extension in ('png','pdf'):fig.savefig(OUT/(name+'.'+extension),dpi=175)
    plt.close(fig)


def figures(v):
    fig,axes=plt.subplots(2,4,figsize=(16,8),layout='constrained',sharey=True)
    kinds=('unmatched','count_only','family_RX_time')
    for i,arm in enumerate(ARMS):
        for j,case in enumerate(CASES):
            ax=axes[i,j];rr=[next(r for r in v['matched_comparisons'] if r['case']==case and r['arm']==arm and r['comparison']==k) for k in kinds]
            for band,color,shift in [('low','#217d8b',-.07),('high','#c8752e',.07)]:
                y=np.array([r[f'{band}_error_mean_km'] for r in rr]);lo=np.array([r[f'{band}_error_min_km'] for r in rr]);hi=np.array([r[f'{band}_error_max_km'] for r in rr])
                ax.errorbar(np.arange(3)+shift,y,yerr=[y-lo,hi-y],fmt='o-',color=color,capsize=3,
                    label='CH1–4' if band=='low' else 'CH5–8')
            full=next(r['error_km'] for r in v['matched_rows'] if r['case']==case and r['arm']==arm and r['method']=='full')
            ax.axhline(full,color='.45',ls=':',label='All curved points')
            ax.set_title(case+' · '+('c=0' if arm=='c0' else 'fitted c'));ax.set_xticks(range(3),['Unmatched','Count\nmatched','Family/RX/time\nmatched'])
            ax.grid(alpha=.2);ax.set_ylim(bottom=0)
            if j==0:ax.set_ylabel('Position error (km)')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Frozen full-data precision and identities; curved evidence only\nBars: range of three predetermined subsamples, not confidence intervals',fontsize=12)
    save(fig,'matched_position_errors')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for k,arm in enumerate(ARMS):
        rr=[next(r for r in v['residual_comparisons'] if r['case']==c and r['arm']==arm and r['mask']=='whole' and r['group']=='all') for c in CASES]
        axes[0].bar(np.arange(4)+(k-.5)*.32,[r['own_model_gain'] for r in rr],.3,color=('#446f92','#2b938c')[k],label=arm)
        for z,predictor in enumerate(('baseline','shared')):
            axes[1].plot(np.arange(4)+(k-.5)*.09,[r[f'movement_gain_{predictor}_predictor'] for r in rr],
                marker=('o','x')[k],ls=('-','--')[z],color=('#446f92','#bd7433')[z],label=f'{arm}; {predictor} predictor')
    for ax in axes:
        ax.axhline(0,color='black',lw=.7);ax.set_xticks(range(4),[c[-4:] for c in CASES]);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    axes[0].set_title('Held whole-family predictive gain');axes[0].set_ylabel('Loss reduction from RX1 correction (positive better)')
    axes[1].set_title('Held evidence supporting position movement');axes[1].set_ylabel('Loss reduction at changed position (positive better)')
    fig.suptitle('Shared RX1 correction: prediction benefit is not consistent support for moving position',fontsize=12)
    save(fig,'receiver_prediction')
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.4),layout='constrained')
    for ax,rx in zip(axes,('RX1','RX2'),strict=True):
        for i,arm in enumerate(ARMS):
            rr=[next(r for r in v['other_receiver_witness'] if r['case']==c and r['arm']==arm and r['target_receiver']==rx) for c in CASES]
            ax.bar(np.arange(4)+(i-.5)*.32,[r['gain_from_other_receiver_family'] for r in rr],.3,label=arm,color=('#446f92','#2b938c')[i])
        ax.set_xticks(range(4),[c[-4:] for c in CASES]);ax.axhline(0,color='black',lw=.7);ax.grid(axis='y',alpha=.2);ax.legend()
        ax.set_title(rx+' held target');ax.set_ylabel('Predictive loss reduction (positive better)')
    fig.suptitle('Does observing this family on the other receiver help?\nSame held IDs; training position and phase refit; conditional fixed-identity diagnostic',fontsize=12)
    save(fig,'other_receiver_witness')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference-latlon',required=True,type=float,nargs=2)
    main(p.parse_args().reference_latlon)
