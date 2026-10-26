"""Saved-artifact reporting only; never invokes a detector or frequency search."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'report'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def metrics(rows):
    result={'n':len(rows),'frequency_numerically_qualified':sum(r['frequency_qualified'] for r in rows),
            'margin_numerically_qualified':sum(r['margin_qualified'] for r in rows)}
    for method in ('old','corrected'):
        x=np.array([r[method+'_error_hz'] for r in rows],float)
        result[method]={'bias_hz':float(np.mean(x)),'rms_hz':float(np.sqrt(np.mean(x*x))),
                        'standard_deviation_hz':float(np.std(x)),'max_abs_error_hz':float(np.max(abs(x)))}
        if rows and rows[0]['panel']=='old24':
            result[method]['lag1_midpoint_error_correlation']=float(np.corrcoef(x[:-1],x[1:])[0,1])
    result['paired_absolute_error_improvements']=sum(abs(r['corrected_error_hz'])<abs(r['old_error_hz']) for r in rows)
    return result


def main():
    seal=json.loads((HERE/'RF_seal.json').read_text())
    for path,digest in seal['files'].items():
        if sha(path)!=digest:raise ValueError('RF artifact changed: '+path)
    execution=json.loads((HERE/'execution.json').read_text());OUT.mkdir(exist_ok=True)
    rows=[];failures=[];raw=[]
    for record in execution['records']:
        q=json.loads(Path(record['file']).read_text())
        if q['status']!='complete':failures.append(q);continue
        r=q['result'];truth=q['generated_truth'];raw.append(q)
        rows.append(dict(panel='old24' if q['name'].startswith('old24') else 'fresh',name=q['name'],
            receiver=q['receiver'],time_s=truth['time_s'],rate_hz_s=truth['rate_hz_s'],
            base_cfo_hz=truth.get('base_cfo_hz',100000.),generated_midpoint_cfo_hz=truth['midpoint_cfo_hz'],
            original_rank=q['original_selected_candidate']['candidate_rank'],
            acquired_cfo_hz=r['acquired_cfo_hz'],original_residual_cfo_hz=r['old_residual_cfo_hz'],
            corrected_residual_cfo_hz=r['exact']['residual_cfo_hz'],old_cfo_hz=r['old_tracking_cfo_hz'],
            corrected_cfo_hz=r['corrected_tracking_cfo_hz'],
            old_error_hz=r['old_tracking_cfo_hz']-truth['midpoint_cfo_hz'],
            corrected_error_hz=r['corrected_tracking_cfo_hz']-truth['midpoint_cfo_hz'],
            old_exact_score=r['old_exact_score'],new_exact_score=r['corrected_exact_score'],
            old_control_score=r['old_control_score'],new_control_score=r['corrected_control_score'],
            old_margin=r['old_exact_score']-r['old_control_score'],new_margin=r['corrected_margin'],
            frequency_qualified=r['numerical_frequency_qualified'],margin_qualified=r['numerical_margin_qualified'],
            exact_reference_difference_hz=r['exact']['reference_frequency_difference_hz'],
            control_reference_difference_hz=r['control']['reference_frequency_difference_hz'],
            original_epoch=r['integer_epoch_sample'],fractional_offset=r['fractional_epoch_offset_samples'],
            source_result=record['file'],result_sha256=record['sha256']))
    rows.sort(key=lambda r:(r['panel'],r['receiver'],r['name']))
    with (OUT/'outcomes.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(protocol_sha256=sha(HERE/'protocol.json'),RF_seal_sha256=sha(HERE/'RF_seal.json'),
        receiver_slots=64,completed=len(rows),failures=failures,
        new_paired_detector_calls=execution['new_paired_detector_calls'],old_full_detector_replays=0,
        cumulative_numerical_worker_seconds=execution['cumulative_worker_seconds'],
        conditions={f'{panel}_RX{rx}':metrics([r for r in rows if r['panel']==panel and r['receiver']==rx])
                    for panel in ('old24','fresh') for rx in (0,1)},
        all_original_residual_bins_zero=all(r['original_residual_cfo_hz']==0 for r in rows),
        exact_grid_max_score_error=max(q['result']['original_grid_closure']['exact_score_error'] for q in raw),
        control_grid_max_score_error=max(q['result']['original_grid_closure']['control_score_error'] for q in raw),
        grid_max_residual_error_hz=max(q['result']['original_grid_closure']['residual_frequency_error_hz'] for q in raw),
        max_direct_score_discrepancy=max(q['result'][k]['direct_score_difference'] for q in raw for k in ('exact','control')),
        max_local_reference_difference_hz=max(q['result'][k]['reference_frequency_difference_hz'] for q in raw for k in ('exact','control')),
        exact_or_control_boundary_count=sum(q['result'][k]['boundary'] for q in raw for k in ('exact','control')),
        minimum_corrected_margin=min(r['new_margin'] for r in rows),
        fixed_candidate_refinement_seconds={'n':len(raw),
            'sum':float(sum(q['seconds'] for q in raw)),
            'median':float(np.median([q['seconds'] for q in raw])),
            'maximum':float(max(q['seconds'] for q in raw))},
        fresh_paired_detector_seconds={'n':8,
            'values':[json.loads(p.read_text())['seconds'] for p in sorted((HERE/'fresh_slots').glob('*.json'))]},
        detector_waveform_count=32,receiver_outputs_are_independent_waveforms=False,
        physical_waveform_validation=False,original_admission_decisions_changed=False)
    write(OUT/'summary.json',summary)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(12.5,8),sharey='row',layout='constrained')
    for rx in (0,1):
        rr=[r for r in rows if r['panel']=='old24' and r['receiver']==rx]
        ax=axes[0,rx]
        ax.plot([r['time_s'] for r in rr],[r['old_error_hz'] for r in rr],'.-',color='.55',label='Original acquisition = final CFO')
        ax.plot([r['time_s'] for r in rr],[r['corrected_error_hz'] for r in rr],'o-',ms=4,color='#176b8b',label='Same score, continuous residual')
        m=summary['conditions'][f'old24_RX{rx}'];ax.set_title(f"Old 24 visits · RX{rx+1} · RMS {m['old']['rms_hz']:.2f} → {m['corrected']['rms_hz']:.2f} Hz")
        ax.set_xlabel('Synthetic global start time (s)');ax.set_ylabel('CFO − generated midpoint (Hz)');ax.axhline(0,color='.2',lw=.7);ax.grid(alpha=.18)
        rr=[r for r in rows if r['panel']=='fresh' and r['receiver']==rx];ax=axes[1,rx];x=np.arange(len(rr))
        ax.plot(x,[r['old_error_hz'] for r in rr],'o',color='.55',label='Original selected output')
        ax.plot(x,[r['corrected_error_hz'] for r in rr],'D',ms=4,color='#176b8b',label='Fixed-candidate correction')
        for i,r in enumerate(rr):ax.plot([i,i],[r['old_error_hz'],r['corrected_error_hz']],color='.75',lw=1,zorder=0)
        labels=[f"{r['base_cfo_hz']/1000:+.3f} kHz\n{r['rate_hz_s']:+.0f} Hz/s, t={r['time_s']:.0f}" for r in rr]
        ax.set_xticks(x,labels,rotation=45,ha='right',fontsize=8)
        m=summary['conditions'][f'fresh_RX{rx}'];ax.set_title(f"Fresh 8 waveforms · RX{rx+1} · RMS {m['old']['rms_hz']:.2f} → {m['corrected']['rms_hz']:.2f} Hz")
        ax.set_ylabel('CFO − generated midpoint (Hz)');ax.axhline(0,color='.2',lw=.7);ax.grid(alpha=.18)
    axes[0,0].legend(fontsize=8);axes[1,0].legend(fontsize=8)
    fig.suptitle('Exact deployed scope64 score: fixed candidate, epoch and original residual cell\nInverse-template controls; no detector admission or recorded-signal validation',fontsize=13)
    fig.savefig(OUT/'frequency_errors.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.4),layout='constrained')
    for panel,marker,color in (('old24','o','#176b8b'),('fresh','D','#b56a16')):
        rr=[r for r in rows if r['panel']==panel]
        axes[0].scatter([r['old_error_hz'] for r in rr],[r['corrected_error_hz'] for r in rr],marker=marker,s=25,label=f'{panel} ({len(rr)} receiver outputs)',color=color,alpha=.7)
        axes[1].scatter([r['new_exact_score']-r['old_exact_score'] for r in rr],[r['new_margin']-r['old_margin'] for r in rr],marker=marker,s=25,label=panel,color=color,alpha=.7)
    axes[0].set(xlabel='Original midpoint error (Hz)',ylabel='Corrected midpoint error (Hz)',title='Held signed controls retain the gain')
    axes[0].axhline(0,color='.3',lw=.7);axes[0].axvline(0,color='.3',lw=.7);axes[0].legend(fontsize=8)
    axes[1].set(xlabel='Increase in exact normalized score',ylabel='Change in exact − control margin',title='Control also refined in its own original cell')
    axes[1].axhline(0,color='.3',lw=.7)
    for ax in axes:ax.grid(alpha=.18)
    fig.suptitle('Numerical frequency closure is separate from detection/admission',fontsize=13)
    fig.savefig(OUT/'score_and_error.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,4),sharey=True,layout='constrained')
    for ax,panel,title in zip(axes,('old24','fresh'),('Old 24 waveforms','Fresh 8 signed controls')):
        xx=np.arange(2)
        for method,offset,color,label in (('old',-.18,'.55','Original selected output'),('corrected',.18,'#176b8b','Continuous residual')):
            yy=[summary['conditions'][f'{panel}_RX{rx}'][method]['rms_hz'] for rx in (0,1)]
            bars=ax.bar(xx+offset,yy,width=.36,color=color,label=label)
            ax.bar_label(bars,fmt='%.2f',padding=3,fontsize=10)
        ax.set_xticks(xx,['RX1','RX2']);ax.set_title(title);ax.grid(axis='y',alpha=.18);ax.set_ylim(0,19)
    axes[0].set_ylabel('RMS CFO error to generated midpoint (Hz)');axes[1].legend(fontsize=8)
    fig.suptitle('Same candidate, epoch, observations and original residual cell',fontsize=12)
    fig.savefig(OUT/'rms_comparison.png',dpi=170);plt.close(fig)
    files=[HERE/'report.py',*sorted(OUT.glob('*.csv')),*sorted(OUT.glob('*.json')),*sorted(OUT.glob('*.png'))]
    files=[p for p in files if p.name!='seal.json']
    write(OUT/'seal.json',dict(RF_seal_sha256=sha(HERE/'RF_seal.json'),files={str(p):sha(p) for p in files}))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
