"""RF-only reporting; no geographic reference or satellite state is imported."""

import csv
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_fft_bias_diagnostic import OUT,PHASES
from run_algo01_ds23_sample import ROOT,read,write,sha


def summarize(rows,rule):
    sums={key:np.sum([r[key] for r in rows],axis=0) for key in
        ('bias_information','bias_residual_cross','fixed_forward_bias_gain')}
    counts=np.array([r['observations'] for r in rows])
    gain=np.array([(r['original_PRESS_energy']-r['corrected_PRESS_energy'])/r['observations'] for r in rows])
    before=sum(r['original_PRESS_sum_squares'] for r in rows)
    after=sum(r['corrected_PRESS_sum_squares'] for r in rows)
    rng=np.random.default_rng(rule['bootstrap_seed'])
    draws=rng.integers(0,len(rows),size=(rule['scan_cluster_bootstrap_samples'],len(rows)))
    boot=gain[draws].mean(axis=1)
    interval=np.quantile(boot,[.025,.975])
    coefficient=np.divide(sums['bias_residual_cross'],sums['bias_information'],
                          out=np.full(16,np.nan),where=sums['bias_information']>0)
    return dict(scans=len(rows),observations=int(counts.sum()),
        forward_fixed_gain=sums['fixed_forward_bias_gain'],forward_coefficient=coefficient,
        zero_phase_control_rank=int(np.argsort(-sums['fixed_forward_bias_gain']).tolist().index(0)+1),
        mean_per_point_weighted_PRESS_gain=float(gain.mean()),bootstrap_95percent_interval=interval,
        original_PRESS_RMS_hz=float(np.sqrt(before/counts.sum())),
        corrected_PRESS_RMS_hz=float(np.sqrt(after/counts.sum())),
        positive_PRESS_scans=int(np.sum(gain>0)),
        qualified=bool(len(rows)>=rule['minimum_scans_in_each_chronological_partition'] and
            sums['fixed_forward_bias_gain'][0]>0 and
            np.argmax(sums['fixed_forward_bias_gain'])==0 and gain.mean()>0 and interval[0]>0))


def main():
    protocol,execution=read(OUT/'protocol.json'),read(OUT/'execution.json')
    rule=read(OUT/'qualification_protocol.json')
    if not execution['all_terminal'] or len(execution['receipts'])!=len(protocol['cases']):
        raise ValueError('every available scan must be terminal')
    for path,digest in protocol['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen RF diagnostic changed')
    if sha(ROOT/'reports/2026_10_19_native_fft_bias/result.json')!=protocol['response_sha256']:
        raise ValueError('fixed response changed')
    groups=defaultdict(list);failures=[];case_rows=[]
    for receipt in execution['receipts']:
        case=receipt['case']
        if 'error' in receipt:failures.append(receipt);continue
        d=read(OUT/(case+'.json'));local={}
        for piece in d['pieces']:
            key=f"{d['format']}/{d['sample_rate_hz']}/{piece['edge']}"
            if key not in local:
                local[key]=dict(case=case,group=key,observations=0,bias_information=np.zeros(16),
                    bias_residual_cross=np.zeros(16),fixed_forward_bias_gain=np.zeros(16),
                    original_PRESS_energy=0.,corrected_PRESS_energy=0.,original_PRESS_sum_squares=0.,corrected_PRESS_sum_squares=0.)
            for k in tuple(local[key]):
                if k not in ('case','group'):local[key][k]+=np.asarray(piece[k])
        for key,row in local.items():
            row['partition']='training' if case in protocol['training_cases'] else 'confirmation'
            groups[key].append(row)
            case_rows.append({k:v for k,v in row.items() if np.asarray(v).ndim==0})
    summary={};eligible=[]
    for key,rows in sorted(groups.items()):
        summary[key]={}
        for partition in ('training','confirmation'):
            selected=[r for r in rows if r['partition']==partition]
            if selected:summary[key][partition]=summarize(selected,rule)
        if len(summary[key])==2 and all(r['qualified'] for r in summary[key].values()):eligible.append(key)
    write(OUT/'evaluation.json',dict(summary=summary,RF_qualified_groups=eligible,failures=failures,
        available_contracts=len(protocol['cases']),population=protocol['population'],unavailable=protocol['unavailable'],
        source_sha256=sha(ROOT/'tools/evaluate_ds23_fft_bias_diagnostic.py'),qualification_protocol_sha256=sha(OUT/'qualification_protocol.json'),
        no_GPS_TLE_or_satellite_fit_used=True,capture_binary_identity_not_certified=True,
        no_position_correction_applied=True,no_claim_of_localization_improvement=True))
    with (OUT/'scan_statistics.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(case_rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(case_rows)
    fig,axes=plt.subplots(len(summary),2,figsize=(13,3.2*len(summary)),squeeze=False)
    for row,(key,parts) in enumerate(summary.items()):
        for partition,color in (('training','#317bb2'),('confirmation','#a363a8')):
            if partition not in parts:continue
            s=parts[partition];axes[row,0].plot(PHASES,s['forward_fixed_gain']/s['observations'],'.-',label=partition,color=color)
            x=0 if partition=='training' else 1;ci=s['bootstrap_95percent_interval'];value=s['mean_per_point_weighted_PRESS_gain']
            axes[row,1].errorbar(x,value,yerr=[[max(0,value-ci[0])],[max(0,ci[1]-value)]],fmt='o',color=color,capsize=4)
        axes[row,0].set(title=key,xlabel='Hypothesis phase shift (Hz)',ylabel='Forward-bias gain per point');axes[row,0].axvline(0,color='gray',ls=':');axes[row,0].legend(fontsize=8)
        axes[row,1].set(title='Fixed inverse response: positive PRESS gain is better',xticks=[0,1],xticklabels=['Earlier 70%','Later 30%'],ylabel='Weighted PRESS gain per point')
        for ax in axes[row]:ax.axhline(0,color='gray',lw=.7);ax.grid(alpha=.15)
    fig.suptitle('DS23: fixed 500 Hz acquisition interpolation-response hypothesis\nCurved RF evidence only; independent point predictions; no TLE, GPS or position fitting')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(OUT/'RF_bias_qualification.png',dpi=170);plt.close(fig)
    print('RF-qualified groups',eligible,'execution failures',len(failures),flush=True)
    print({k:{p:{q:s[q] for q in ('scans','observations','zero_phase_control_rank','original_PRESS_RMS_hz','corrected_PRESS_RMS_hz','qualified')}
              for p,s in v.items()} for k,v in summary.items()},flush=True)


if __name__=='__main__':main()
