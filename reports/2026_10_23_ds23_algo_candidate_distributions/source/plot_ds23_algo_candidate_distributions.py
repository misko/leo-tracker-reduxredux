"""Matched distributions of frozen full-DS23 candidate results; no new fits."""

import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/2026_10_23_ds23_algo_candidate_distributions'
INPUTS={
    'families':ROOT/'reports/2026_10_22_ds23_dbg01_iteration_007/tables/full_DS23_positions.csv',
    'guard':ROOT/'reports/2026_10_22_ds23_dbg01_iteration_011/tables/full_DS23_positions.csv',
    'deadline':ROOT/'reports/2026_10_23_ds23_completed_deadline_assessment/tables/positions.csv',
    'benchmark':ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv',
    'metadata':ROOT/'reports/2026_10_19_algo02_ds23_full/sample.json',
}
METHODS=['Reference','Grouped new families','Paired RF guard','Completed-candidate retention']
COLORS=['#222222','#2878B5','#319B69','#E18B24']
FORMAT_NAMES={'short_window_iq_recording':'Fast','starlink_adaptive_hop_iq':'Adaptive'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_read(path):
    with path.open(newline='') as stream:return list(csv.DictReader(stream))


def keyed(rows,method,error_key):
    result={}
    for row in rows:
        if row['method']!=method:continue
        key=(row['arm'],row['case']);error=float(row[error_key])
        if key in result:raise ValueError('duplicate arm/case in candidate distribution')
        if not np.isfinite(error) or error<0:raise ValueError('finite nonnegative position error required')
        result[key]=dict(row,error_km=error)
    return result


def align(reference,candidate):
    if set(reference)!=set(candidate):raise ValueError('candidate and reference must contain the exact same cases and arms')
    return [(key,reference[key],candidate[key]) for key in sorted(reference)]


def empirical(values):
    values=np.asarray(values,float)
    if values.ndim!=1 or not len(values) or not np.isfinite(values).all() or np.any(values<0):raise ValueError('nonempty finite nonnegative errors required')
    x,count=np.unique(values,return_counts=True);cdf=np.cumsum(count)/len(values)
    survival=(len(values)-np.r_[0,np.cumsum(count)[:-1]])/len(values)
    return x,cdf,survival


def load():
    family=csv_read(INPUTS['families']);guard=csv_read(INPUTS['guard']);deadline=csv_read(INPUTS['deadline'])
    reference=keyed(family,'incumbent','position_error_km')
    maps=[reference,keyed(family,'physical_prior','position_error_km'),keyed(guard,'paired_positive','position_error_km'),keyed(deadline,'Completed deadline candidate','error_km')]
    benchmark={(r['arm'],r['case']):float(r['policy_error_km']) for r in csv_read(INPUTS['benchmark']) if r['policy']=='equal_assignment_priors'}
    if len(reference)!=820 or set(reference)!=set(benchmark):raise ValueError('exactly410 published scans in both arms required')
    for other in [keyed(guard,'published_c0_positive','position_error_km'),keyed(deadline,'Incumbent','error_km')]:
        for key,a,b in align(reference,other):
            if abs(a['error_km']-b['error_km'])>1e-8:raise ValueError('source reference errors differ')
    if any(abs(r['error_km']-benchmark[k])>1e-8 for k,r in reference.items()):raise ValueError('published reference does not reproduce')
    metadata={r['dataset_label']:r for r in json.loads(INPUTS['metadata'].read_text())['selected']}
    rows=[]
    for method,mapping in zip(METHODS,maps,strict=True):
        for (arm,case),old,new in align(reference,mapping):
            rows.append(dict(case=case,arm=arm,method=method,error_km=new['error_km'],reference_error_km=old['error_km'],
                error_change_m=1000*(new['error_km']-old['error_km']),format=FORMAT_NAMES[metadata[case]['recording_format']],
                associated_points=int((old if method=='Paired RF guard' else new)['associated_points']),
                total_GLRT=int(old['total_GLRT'])))
    return rows


def summarize(rows):
    x=np.array([r['error_km'] for r in rows]);delta=np.array([r['error_change_m'] for r in rows]);n=len(rows)
    return dict(scans=n,mean_error_km=float(x.mean()),median_error_km=float(np.median(x)),P90_km=float(np.percentile(x,90)),P95_km=float(np.percentile(x,95)),
        maximum_error_km=float(x.max()),within0p5km=int(np.sum(x<=.5)),within0p5km_percent=float(100*np.mean(x<=.5)),
        within1km=int(np.sum(x<=1)),within2km=int(np.sum(x<=2)),
        improved_over1m=int(np.sum(delta < -1)),worsened_over1m=int(np.sum(delta > 1)),within1m_of_reference=int(np.sum(abs(delta)<=1)),
        associated_points=sum(r['associated_points'] for r in rows),total_GLRT=sum(r['total_GLRT'] for r in rows),
        associated_percent=100*sum(r['associated_points'] for r in rows)/sum(r['total_GLRT'] for r in rows))


def distribution_figure(rows,arm):
    fig,axes=plt.subplots(1,2,figsize=(17,6),layout='constrained')
    for method,color in zip(METHODS,COLORS,strict=True):
        rr=[r for r in rows if r['method']==method and r['arm']==arm];x,cdf,survival=empirical([r['error_km'] for r in rr])
        style=dict(color=color,lw=2.6 if method=='Reference' else 1.9,ls='--' if method=='Reference' else '-',label=method)
        axes[0].step(np.r_[0,x],np.r_[0,cdf]*100,where='post',**style)
        axes[1].step(x,survival*100,where='pre',**style)
    axes[0].set(xlim=(0,4),ylim=(0,100),xlabel='Position error (km)',ylabel='Scans at or below error (%)',title='Main distribution · higher curve is better')
    axes[1].set(xlim=(0,18),ylim=(.2,100),yscale='log',xlabel='Position error (km)',ylabel='Scans at or above error (%)',title='Full tail · lower curve is better; all outliers retained')
    for ax in axes:ax.axvline(.5,c='#9D3A5B',ls=':',lw=1.6,label='0.5 km goal');ax.grid(alpha=.22,which='both');ax.legend(fontsize=9,loc='lower right' if ax is axes[0] else 'upper right')
    fig.suptitle(f"DS23 · {'fitted c' if arm=='fitted_c' else 'c = 0'} · same410 scans · three separate candidate policies\nCached published results; original reference retained; candidate combination has not been evaluated",fontsize=13)
    fig.savefig(OUT/'figures'/f'{arm}_error_distribution.png',dpi=160);plt.close(fig)


def format_figure(rows):
    fig,axes=plt.subplots(1,2,figsize=(17,6),layout='constrained')
    for ax,fmt,n in zip(axes,['Fast','Adaptive'],[204,206],strict=True):
        for method,color in zip(METHODS,COLORS,strict=True):
            rr=[r for r in rows if r['arm']=='fitted_c' and r['format']==fmt and r['method']==method]
            if len(rr)!=n:raise ValueError('format counts changed')
            x,cdf,_=empirical([r['error_km'] for r in rr]);ax.step(np.r_[0,x],np.r_[0,cdf]*100,where='post',color=color,lw=2.6 if method=='Reference' else 1.9,ls='--' if method=='Reference' else '-',label=method)
        ax.set(title=f'{fmt} scans · n={n}',xlim=(0,4),ylim=(0,100),xlabel='Position error (km)',ylabel='Scans at or below error (%)');ax.axvline(.5,c='#9D3A5B',ls=':',label='0.5 km goal');ax.grid(alpha=.22);ax.legend(fontsize=9,loc='lower right')
    fig.suptitle('DS23 · fitted c · distribution by scan format\nCentral0–4km view; the separate full-tail figure retains every scan and outlier',fontsize=13)
    fig.savefig(OUT/'figures/fast_adaptive_distributions.png',dpi=160);plt.close(fig)


def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    for folder in ['figures','tables','source','evidence']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    rows=load();summary=[]
    for arm in ['fitted_c','c0']:
        for group in ['All','Fast','Adaptive']:
            for method in METHODS:
                selected=[r for r in rows if r['arm']==arm and r['method']==method and (group=='All' or r['format']==group)]
                summary.append(dict(arm=arm,group=group,method=method,**summarize(selected)))
        distribution_figure(rows,arm)
    format_figure(rows);write_csv(OUT/'tables/positions.csv',rows);write_csv(OUT/'tables/summary.csv',summary)
    shutil.copyfile(Path(__file__),OUT/'source'/Path(__file__).name)
    shutil.copyfile(ROOT/'tests/analysis/test_ds23_candidate_distributions.py',OUT/'source/test_ds23_candidate_distributions.py')
    receipt=dict(all_passed=True,exact_same410cases_in_both_arms_and_all_four_methods=True,reference_agrees_across_three_publications_and_benchmark_to1e_minus8km=True,
        unavailable=['DS23-0012','DS23-0184','DS23-0286'],inherited_phase_exception0068_retained_in_every_distribution=True,
        c0_and_fitted_c_are_separate_matched_arms=True,no_new_fit_inference_or_policy_selection=True,new_ALGO_release=False,
        cohorts_same_site_previously_studied_not_new_location_validation=True,
        source_hashes={str(path.relative_to(ROOT)):sha(path) for path in [*INPUTS.values(),Path(__file__),ROOT/'tests/analysis/test_ds23_candidate_distributions.py']},
        summary=summary)
    (OUT/'evidence/reproduction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps([s for s in summary if s['group']=='All'],indent=2))


if __name__=='__main__':main()
