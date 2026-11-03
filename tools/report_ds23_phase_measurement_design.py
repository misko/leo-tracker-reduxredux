"""Scientific figures for hypothetical independent timing information only."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_phase_measurement_design import OUT,BULK
from probe_ds23_synthetic_known_nuisance import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def main():
    audit=read(OUT/'independent_audit.json');protocol=read(OUT/'protocol.json');cases=protocol['cases']
    assert audit['all_checks_pass'] and audit['endpoint_arms']==1040
    rows=audit['rows'];summaries=audit['summary']
    baseline={a:[] for a in ['c0','fitted_c']}
    for case in cases:
        old=read(SOURCE/(case+'_draw0_all.json'))
        for arm in baseline:baseline[arm].append(old['arms'][arm]['synthetic_position_error_km'])
    def get(method,draw,arm):
        return next(r for r in summaries if r['method']==method and r['draw']==draw and r['arm']==arm)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for ax,arm in zip(axes,['c0','fitted_c'],strict=True):
        for suffix,color,label in [('0.1','#df801b','0.1 s timing SD'),('002','#168b91','0.02 s timing SD')]:
            names=([f'information_{k}_sd0.1' for k in [1,3,6]]+['information_all_sd01'] if suffix=='0.1'
                   else [f'information_{k}_sd002' for k in [1,3,6]]+['information_all_sd002'])
            mean=[np.mean(baseline[arm])]+[get(n,0,arm)['mean_km'] for n in names]
            median=[np.median(baseline[arm])]+[get(n,0,arm)['median_km'] for n in names]
            ax.plot(range(5),mean,'o-',color=color,label=label+' · mean')
            ax.plot(range(5),median,'s--',color=color,alpha=.7,label=label+' · median')
        ax.axhline(.5,color='black',ls=':',label='0.5 km target')
        ax.set_xticks(range(5),['0','1','3','6','All eligible\n12–24 families'])
        ax.set(xlabel='Number of independently measured satellite timings',ylabel='Position error (km)',title=arm)
        ax.grid(alpha=.2);ax.set_ylim(bottom=0)
    axes[1].legend(fontsize=8,loc='upper right')
    fig.suptitle('Conditional simulations on 20 fixed DS23 templates · first timing-noise draw')
    fig.text(.5,.005,'Original RF gates retained; failed pairs fall back. Hypothetical timing measurements; no real DS23 accuracy gain.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.035,1,.95]);fig.savefig(OUT/'timing_precision_and_count.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    settings=[('information_6_sd0.1','six_sd01/information','#df801b','6 families, timing SD 0.1 s'),
              ('information_3_sd002','three_sd002/information','#168b91','3 families, timing SD 0.02 s'),
              ('point_count_3_sd002','three_sd002/point_count','#777777','3 largest families, SD 0.02 s'),
              ('random_3_sd002','three_sd002/random','#9870ad','3 random families, SD 0.02 s')]
    for col,arm in enumerate(['c0','fitted_c']):
        for row,metric in enumerate(['mean_km','median_km']):
            ax=axes[row,col]
            for first,later,color,label in settings:
                values=[get(first,0,arm)[metric]]+[get(later,k,arm)[metric] for k in [1,2]]
                ax.plot([0,1,2],values,'o-',color=color,label=label)
            ax.axhline(.5,color='black',ls=':');ax.grid(alpha=.2);ax.set_ylim(bottom=0)
            ax.set(title=arm+' · '+metric.replace('_km',''),ylabel='Position error (km)',xticks=[0,1,2])
            if row==1:ax.set_xlabel('Independent hypothetical timing-noise draw')
    axes[0,1].legend(fontsize=8)
    fig.suptitle('Timing-noise replication · same 20 radio templates, unchanged priors and gates')
    fig.text(.5,.005,'Each point summarizes 20 templates. Repeated noise draws are not additional independent scans. No real-data improvement is claimed.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.03,1,.95]);fig.savefig(OUT/'timing_noise_replication.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,4.8));x=np.arange(len(cases));base=baseline['fitted_c']
    ax.plot(x,base,'o-',color='#999999',label='Original synthetic baseline')
    for first,later,color,label in settings[:2]:
        values=[]
        for case in cases:
            rr=[r['policy_error_km'] for r in rows if r['case']==case and r['arm']=='fitted_c'
                and ((r['method']==first and r['draw']==0) or r['method']==later)]
            assert len(rr)==3;values.append(rr)
        values=np.asarray(values)
        ax.errorbar(x,values.mean(axis=1),yerr=np.vstack((values.mean(axis=1)-values.min(axis=1),values.max(axis=1)-values.mean(axis=1))),
            fmt='o',color=color,capsize=2,label=label+' · mean and noise-draw range')
    ax.axhline(.5,color='black',ls=':');ax.set_xticks(x,[c.split('-')[1] for c in cases],rotation=60)
    ax.set(xlabel='DS23 template (simulation, fitted c)',ylabel='Position error (km)',title='Per-template sensitivity to independent timing information')
    ax.grid(alpha=.2);ax.legend(fontsize=8);fig.tight_layout();fig.savefig(OUT/'timing_information_per_template.png',dpi=160);plt.close(fig)
    targets=[]
    for case in cases+['DS23-0268','DS23-0405']:
        d=read(BULK/(case+'_design.json'));selection=d['variants']['information_6_sd0.1']
        for rank,(k,h) in enumerate(zip(selection['label_indices'],selection['history'],strict=True),1):
            targets.append(dict(case=case,rank=rank,norad=d['norads'][k],curved_points=d['design']['curved_point_counts'][k],
                local_position_variance_gain_km2=h['gain_km2'],hypothetical_timing_SD_s=.1,
                engineering=case in ['DS23-0268','DS23-0405']))
    with (OUT/'timing_targets.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(targets[0]));writer.writeheader();writer.writerows(targets)
    with (OUT/'timing_policy_summary.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    original=ROOT/'reports/2026_10_20_ds23_combined_recovery_full/evaluation.json';all_rows=read(original)['all_rows']
    benchmark={}
    for arm in ['c0','fitted_c']:
        accepted=[r for r in all_rows if r['method']=='signed_prior' and r['arm']==arm and r['status']=='accepted']
        assert len(accepted)==410;errors=[r['position_error_km_report_only'] for r in accepted]
        benchmark[arm]=dict(n=410,mean_km=float(np.mean(errors)),median_km=float(np.median(errors)))
    receipt=dict(figures=['timing_precision_and_count.png','timing_noise_replication.png','timing_information_per_template.png'],
        audit_sha256=sha(OUT/'independent_audit.json'),full_DS23_benchmark=benchmark,
        full_DS23_evaluation_sha256=sha(original),real_accuracy_gain=False,publication_not_qualified=True,
        reason='Independent timing information is hypothetical, not a measured or validated causal input')
    write(OUT/'figure_and_benchmark_receipt.json',receipt);print(receipt,flush=True)


if __name__=='__main__':main()
