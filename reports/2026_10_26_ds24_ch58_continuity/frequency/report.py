"""Offline summary/figures/seal; no IQ or estimator scoring calls."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def saved(fig,name):
    fig.savefig(HERE/(name+'.png'),dpi=170,bbox_inches='tight')
    fig.savefig(HERE/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def exact_upper95(k,n):
    if k==n:return 1.
    if k==0:return 1.-.05**(1./n)
    left,right=0.,1.
    for _ in range(80):
        p=(left+right)/2
        cdf=sum(math.comb(n,j)*p**j*(1-p)**(n-j) for j in range(k+1))
        if cdf>.05:left=p
        else:right=p
    return (left+right)/2


def main():
    began=time.monotonic()
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal=__import__('signal')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580-second report bound')))
    signal.alarm(580)
    checks={}
    for manifest in ['protocol.json','natural_protocol.json','interval_audit_v2_protocol.json']:
        p=read(HERE/manifest)
        checks[manifest]=all(sha(path)==digest for path,digest in p['files'].items())
    run=subprocess.run([sys.executable,'-m','unittest','-v','test_estimator','test_natural_adapter',
        'test_interval_audit_v2'],cwd=HERE,text=True,capture_output=True,timeout=60)
    if not (HERE/'test_results.json').exists():
        write(HERE/'test_results.json',dict(command=run.args,exit_code=run.returncode,
            stdout=run.stdout,stderr=run.stderr,expected_tests=11))
    elif read(HERE/'test_results.json')['exit_code']!=run.returncode:
        raise RuntimeError('current tests differ from retained receipt')
    if run.returncode:raise RuntimeError('owned tests failed')
    s=read(HERE/'synthetic.json');recorded=read(HERE/'recorded.json');null=read(HERE/'null.json')
    audit=read(HERE/'interval_audit_v2.json');natural=read(HERE/'natural_qualification.json')
    signals=s['rows'];cells=[dict(c,request_id=r['request_id']) for r in recorded['rows'] for c in r['cells']]
    methods=['unchanged','carry','proposal']
    accuracy={str(db):dict(n=sum(r['db']==db for r in signals),
        accurate={m:sum(r['evaluation']['accurate'][m] for r in signals if r['db']==db) for m in methods})
        for db in [-12,-24]}
    evolution=[r for r in signals if r['db']==-12 and r['donor_error_hz']==0 and
        r['forecast']=='zero_rate' and r['true_rate_hz_s']!=0]
    slope=sum(r['true_rate_hz_s']*.354*r['evaluation']['proposal_change_from_carry_hz'] for r in evolution)/sum(
        (r['true_rate_hz_s']*.354)**2 for r in evolution)
    evolacc=sum(r['evaluation']['accurate']['proposal'] for r in evolution)
    nullstats=[]
    for count in [1,3]:
        rows=[r for r in null['rows'] if r['proposal_count']==count]
        k=sum(r['false_confirmation'] for r in rows);n=len(rows)
        upper=exact_upper95(k,n)
        nullstats.append(dict(proposals=count,n=n,false_confirmations=k,upper95=upper))
    recaccuracy={m:sum(bool(c['estimate']['primary'] and c['estimate']['primary']['passed_gate'] and
        c['evaluation']['accurate'][m] and abs(c['donor_truth_evaluation'][0]['timing_error_samples'])<=2)
        for c in cells) for m in methods}
    corrected=audit['totals']['synthetic']['covered']['bin_density']/audit['totals']['synthetic']['n']
    screen=dict(strong_evolution_accuracy=evolacc/len(evolution)>=.8,
        evolution_slope=.5<=slope<=1.5,conditional_interval_coverage=corrected>=.9,
        primary_and_three_proposal_null_upper95=all(r['upper95']<=.05 for r in nullstats))
    # True timing is evaluation only, including wrong/missing donors in totals.
    correct_donors=[c for c in cells if c['estimate']['primary'] and c['donor_truth_evaluation'][0]['matched']]
    rmse={m:float(np.sqrt(np.mean([c['evaluation']['errors_hz'][m]**2 for c in correct_donors])))
        for m in methods}
    summary=dict(schema='frequency-continuity-summary/v1',status='RF_NOT_QUALIFIED',
        reason='Recorded accuracy does not improve, RF scale is uncalibrated, and every eligible natural history fails later support',
        synthetic_accuracy=accuracy,synthetic_conditional_screen=screen,synthetic_screen_pass=all(screen.values()),
        independent_synthetic_later_noise_vectors=s['independent_later_noise_vectors'],
        synthetic_conditional_comparisons=len(signals),evolution=dict(n=len(evolution),accurate=evolacc,slope=slope),
        interval_reporting_audit=audit['totals'],conditional_null=nullstats,
        recorded=dict(n=len(cells),correct_primary_donors=len(correct_donors),accurate=recaccuracy,
            correct_donor_CFO_RMSE_hz=rmse,no_donor=sum(c['estimate']['primary'] is None for c in cells),
            unchanged_round3_scores_equal=all(c['unchanged_round3_equal'] for c in cells)),
        natural=dict(receiver_cells=natural['receiver_cells'],eligible_cells=natural['eligible_cells'],
            eligible_modes=natural['eligible_modes'],supported_modes=natural['supported_modes'],
            IQ_reads=0,frequency_calls=0,position_calls=0),
        seconds=dict(synthetic=s['seconds'],null=null['seconds'],recorded=recorded['seconds'],
            natural_metadata=natural['seconds'],interval_offline=audit['seconds']),
        later_profile_is_separate_from_donor_posterior=True,uncertainty_weights_qualified=False,
        independent_added_Doppler_points=0)
    write(HERE/'summary.json',summary)
    with (HERE/'cells.csv').open('x') as f:
        names=['request_id','receiver_id','donor_status','gate','unchanged_error_hz','carry_error_hz','proposal_error_hz',
            'unchanged_accurate','carry_accurate','proposal_accurate','round3_score_equal']
        writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
        for c in cells:
            e=c['evaluation'];primary=c['estimate']['primary']
            writer.writerow(dict(request_id=c['request_id'],receiver_id=c['receiver_id'],
                donor_status='correct_injected' if c in correct_donors else 'wrong_or_absent',
                gate=bool(primary and primary['passed_gate']),round3_score_equal=c['unchanged_round3_equal'],
                **{m+'_error_hz':e.get('errors_hz',{}).get(m,'') for m in methods},
                **{m+'_accurate':e.get('accurate',{}).get(m,False) if primary else False for m in methods}))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors=['#a34848','#797979','#226b9a'];labels=['Unchanged later bin','Donor carry (copied)','Complex-profile proposal']
    fig,axes=plt.subplots(1,3,figsize=(13,3.6))
    for ax,db in zip(axes[:2],[-12,-24]):
        counts=accuracy[str(db)]['accurate'];ax.bar(np.arange(3),[counts[m] for m in methods],color=colors)
        ax.set_xticks(np.arange(3),['Later bin','Carry','Proposal']);ax.set_ylim(0,160)
        ax.set_title(f'Synthetic {db} dB: /144 comparisons');ax.set_ylabel('CFO within 100 Hz')
        for i,m in enumerate(methods):ax.text(i,counts[m]+3,str(counts[m]),ha='center')
    for i,(rate,marker) in enumerate([(-2000.,'o'),(2000.,'s')]):
        a=[r for r in evolution if r['true_rate_hz_s']==rate]
        axes[2].scatter([rate*.354]*len(a),[r['evaluation']['proposal_change_from_carry_hz'] for r in a],
            marker=marker,s=36,alpha=.75,label=f'{rate:+g} Hz/s')
    axes[2].plot([-1000,1000],[-1000,1000],'k--',lw=1)
    axes[2].set(xlabel='True change across 0.354 s (Hz)',ylabel='Proposal change from donor (Hz)',
        title=f'Mistaken zero-rate forecast; slope {slope:.3f}')
    axes[2].legend(fontsize=8);fig.suptitle('Synthetic mechanism: strong evolution preserved; weak accuracy does not improve')
    fig.tight_layout();saved(fig,'synthetic_accuracy_and_evolution')

    fig,axes=plt.subplots(1,2,figsize=(12,4.5),gridspec_kw={'width_ratios':[2.2,1]})
    x=np.arange(len(cells))
    for j,m in enumerate(methods):
        y=[c['evaluation'].get('errors_hz',{}).get(m,np.nan) for c in cells]
        axes[0].scatter(x+(j-1)*.17,y,s=24,color=colors[j],label=labels[j])
    axes[0].set_yscale('symlog',linthresh=500);axes[0].axhspan(-100,100,color='#dbeedb',alpha=.8)
    axes[0].axhline(0,color='k',lw=.5);axes[0].set_xticks(x,[f"{c['request_id'].replace('DS24-00','')}/R{c['receiver_id']}" for c in cells],rotation=65,ha='right',fontsize=7)
    axes[0].set(ylabel='CFO error (Hz), symmetric log scale',title='All 16 recorded-background cells; missing donor retained')
    axes[0].legend(fontsize=8)
    axes[1].bar(np.arange(3),[recaccuracy[m] for m in methods],color=colors)
    axes[1].set_xticks(np.arange(3),['Later bin','Carry','Proposal']);axes[1].set_ylim(0,16)
    axes[1].set(ylabel='Accurate injected recovery /16',title='Fixed gate, timing <=2 samples, CFO <=100Hz')
    for i,m in enumerate(methods):axes[1].text(i,recaccuracy[m]+.3,str(recaccuracy[m]),ha='center')
    fig.suptitle('The proposed estimator does not fix the recorded-background recovery failure')
    fig.tight_layout();saved(fig,'recorded_frequency_errors')

    fig,axes=plt.subplots(4,4,figsize=(14,10),sharex=True)
    for ax,c in zip(axes.flat,cells):
        primary=c['estimate']['primary'];ax.set_title(f"{c['request_id'].replace('DS24-00','')}, RX{c['receiver_id']}",fontsize=9)
        if not primary:ax.text(.5,.5,'No donor',ha='center',transform=ax.transAxes);continue
        p=primary['proposed'];g=np.asarray(p['grid_offsets_hz'])
        ll=np.asarray(p['relative_log_likelihood']);w=np.asarray(p['conditional_grid_weights'])
        logw=np.log(np.maximum(w,1e-300));logw-=max(logw)
        ax.plot(g,ll,color='#a34848',lw=1,label='Later profile only')
        ax.plot(g,logw,color='#226b9a',lw=1,label='Donor-conditioned')
        truth=213456.75-primary['predicted_cfo_hz']
        if -3000<=truth<=3000:ax.axvline(truth,color='k',ls='--',lw=.7)
        ax.set_ylim(-20,1);ax.axvline(0,color='#999999',lw=.5)
    for ax in axes[-1]:ax.set_xlabel('Residual CFO from earlier forecast (Hz)')
    for ax in axes[:,0]:ax.set_ylabel('Relative log score')
    axes.flat[0].legend(fontsize=7)
    fig.suptitle('Later complex-data profile and conditioned score are distinct; neither is calibrated RF uncertainty')
    fig.tight_layout();saved(fig,'recorded_profiles_and_conditioning')

    fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    for j,kind in enumerate(['synthetic','recorded']):
        total=audit['totals'][kind];values=[total['covered'][k]/total['n'] for k in ['frozen_v1','discrete_mass','bin_density']]
        axes[0].plot(range(3),values,'o-',label=f"{kind} (n={total['n']})")
    axes[0].axhline(.95,color='k',ls='--',lw=.8);axes[0].set_xticks(range(3),['Frozen v1','Discrete mass','Bin density'],rotation=20)
    axes[0].set(ylim=(0,1.05),ylabel='Descriptive 95% interval coverage',title='Offline interval reporting sensitivity');axes[0].legend(fontsize=8)
    axes[1].bar(range(2),[r['upper95']*100 for r in nullstats],color='#8274a1')
    axes[1].set_xticks(range(2),['1 proposal','3 proposals'])
    axes[1].set(ylabel='One-sided 95% FAR upper bound (%)',title='Conditional synthetic nulls: 0/64 each',ylim=(0,6))
    axes[2].bar(range(3),[96,5,0],color=['#999999','#b08a42','#226b9a'])
    axes[2].set_xticks(range(3),['All cells','Donor eligible','Later support'],rotation=15)
    axes[2].set(ylabel='Natural receiver cells',title='Frozen natural prerequisite fails',ylim=(0,105))
    fig.tight_layout();saved(fig,'uncertainty_null_and_natural')
    checks.update(tests_passed=run.returncode==0,tests=11,expected_recorded_cells=len(cells)==16,
        all_recorded_slots_complete=all(r['status']=='complete' for r in recorded['rows']),
        historical_unchanged_score_parity=summary['recorded']['unchanged_round3_scores_equal'],
        synthetic_comparisons=len(signals)==288,synthetic_independent_vectors=s['independent_later_noise_vectors']==48,
        null_vectors=len(null['rows'])==128,distinct_null_vectors=len({r['later_sha256'] for r in null['rows']})==128,
        absent_no_donor_calls=len(null['absent'])==6,all_natural_cells=natural['receiver_cells']==96,
        natural_stopped_at_failed_prerequisite=natural['natural_frequency_estimator_calls']==0 and natural['new_IQ_reads']==0,
        no_uncertainty_qualification=True,no_position_calls=True,
        runtime_bounds=all(v<580 for v in summary['seconds'].values()))
    write(HERE/'verification.json',dict(checks=checks,all_passed=all(bool(v) for v in checks.values()),
        seconds=time.monotonic()-began,RF_qualified=False))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
