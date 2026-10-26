"""Paired R02 full-window diagnostics, no target-selected method or positions."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
METHODS=['linear','quadratic_or_fallback','legacy_adapter_linear']
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def save(fig,name):
    fig.savefig(HERE/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(HERE/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def stats(rows):
    return dict(n=len(rows),original=sum(r['original_pass'] for r in rows),
        r01_search=sum(r['r01_search'] for r in rows),
        methods={m:dict(admitted=sum(r[m+'_admitted'] for r in rows),
            pilot=sum(r[m+'_pilot'] for r in rows),new_original_absent=sum(r[m+'_admitted'] and not r['original_pass'] for r in rows)) for m in METHODS},
        quadratic_gain_vs_linear=sum(r['quadratic_or_fallback_admitted'] and not r['linear_admitted'] for r in rows),
        quadratic_loss_vs_linear=sum(r['linear_admitted'] and not r['quadratic_or_fallback_admitted'] for r in rows))


def main():
    p=read(HERE/'protocol.json');rows=[];execution=[];candidates=[];failures=[]
    for case in p['development']:
        source=HERE/'outcomes'/(case+'.json.gz');value=read(source)
        old={c['prediction_id']:c for r in read(R01/'timing/outcomes'/(case+'.json.gz'))['rows'] for c in r['cells']}
        readtime=scoretime=0.
        for w in value['rows']:
            if w['status']!='complete':failures.append(dict(request_id=w['request_id'],error=w.get('error')))
            readtime+=w.get('native_read_receipt',{}).get('native_read_verify_seconds',0.)
            for c in w['cells']:
                pred=c['prediction'];r=c['result'];o=old[c['prediction_id']]
                original=any(x['passed_fractional_margin_gate'] for x in o['original_fullwindow'].get('candidates',[]))
                oldsearch=o['result'].get('search');scoretime+=c['scoring_seconds']
                row=dict(prediction_id=c['prediction_id'],owner_id=r['owner_id'],case=case,channel=w['channel'],receiver_id=c['receiver_id'],
                    model_status=pred['status'],original_pass=original,r01_search=bool(oldsearch and oldsearch['evaluation']['admitted']),
                    donor_count=len(pred['donors']),scoring_seconds=c['scoring_seconds'])
                for m in METHODS:
                    item=r['methods'].get(m)
                    row.update({m+'_admitted':bool(item and item['admitted']),m+'_pilot':bool(item and item['pilot_confirmed']),
                        m+'_margin':item['score'].get('margin','') if item else '',m+'_CFO_hz':item['score'].get('tracking_cfo_hz','') if item else '',
                        m+'_innovation_hz':item['frequency_innovation_hz'] if item else '',m+'_epoch_samples':item['point']['epoch_samples'] if item else ''})
                rows.append(row)
                if r.get('operational_admitted'):
                    item=r['methods']['quadratic_or_fallback'];h=pred['header']
                    candidates.append(dict(prediction_id=c['prediction_id'],owner_id=r['owner_id'],case=case,channel=w['channel'],receiver_id=c['receiver_id'],
                        visit_index=h['visit_index'],probe_index=h['probe_index'],target_support=r['target_support'],donors=pred['donors'],
                        primary_hypothesis_id=pred['primary_hypothesis_id'],model_status=pred['status'],point=item['point'],score=item['score'],
                        frequency_innovation_hz=item['frequency_innovation_hz'],original_pass=original,
                        action='alternative_on_existing_owner' if original else 'newly_confirmed_native_owner',
                        provisional=True,no_automatic_replacement=True,uncertainty_weights_qualified=False,independent_added_Doppler_points=0))
        execution.append(dict(case=case,seconds=value['seconds'],read_verify_seconds=readtime,score_seconds=scoretime,
            residual_seconds=value['seconds']-readtime-scoretime,paired_windows=len(value['rows']),cells=sum(len(r['cells']) for r in value['rows']),source_sha256=sha(source)))
    innovation={}
    for m in METHODS:
        accepted=[r for r in rows if r[m+'_admitted']];x=np.array([r[m+'_innovation_hz'] for r in accepted])
        innovation[m]=dict(n=len(x),zero_bins=int(np.sum(abs(x)<1e-6)),nonzero_bins=int(np.sum(abs(x)>=1e-6)),
            max_absolute_hz=float(np.max(abs(x))) if len(x) else None,
            median_absolute_hz=float(np.median(abs(x))) if len(x) else None,
            all_multiple_443_892045Hz=bool(np.all(abs(x/(10_000_000/(44*512))-np.rint(x/(10_000_000/(44*512))))<1e-8)))
    summary=dict(schema='round2-fullwindow-development-summary/v2',requested_windows=288,requested_cells=576,observed_cells=len(rows),
        unique_native_owners=len({r['owner_id'] for r in rows}),counts=stats(rows),
        by_channel={str(ch):stats([r for r in rows if r['channel']==ch]) for ch in [1,4,5,6,7,8]},
        CH5_8=stats([r for r in rows if r['channel']>=5]),
        by_model_status={k:stats([r for r in rows if r['model_status']==k]) for k in ['quadratic','linear_fallback','no_donor']},
        by_channel_receiver={f'CH{ch}/RX{rx}':stats([r for r in rows if r['channel']==ch and r['receiver_id']==rx]) for ch in [1,4,5,6,7,8] for rx in [0,1]},
        innovations=innovation,execution=execution,failed_windows=failures,
        summed_runtime_seconds=sum(e['seconds'] for e in execution),native_read_verify_seconds=sum(e['read_verify_seconds'] for e in execution),
        new_scoring_seconds=sum(e['score_seconds'] for e in execution),repeated_blind_acquisition_calls=0,
        reused_exact_R01_per_window_parity=True,ready_for_coherence_review=True,ready_for_position=False,
        independent_added_Doppler_points=0,uncertainty_qualified=False,protocol_sha256=sha(HERE/'protocol.json'))
    write(HERE/'recorded_summary.json',summary)
    with (HERE/'recorded_cells.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(HERE/'candidate_manifest.json',dict(schema='round2-primary-candidates/v2',candidates=candidates,
        operational_method='quadratic_or_fallback',no_best_method_selection=True,position_ready=False,
        independent_added_Doppler_points=0,source_protocol_sha256=sha(HERE/'protocol.json')))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4));channels=[1,4,5,6,7,8];colors=['#777777','#246b99','#a37b42']
    for j,m in enumerate(METHODS):
        axes[0].bar(np.arange(6)+(j-1)*.23,[summary['by_channel'][str(ch)]['methods'][m]['admitted'] for ch in channels],width=.22,color=colors[j],label={'linear':'Consistent linear','quadratic_or_fallback':'Quadratic / fallback','legacy_adapter_linear':'Legacy adapter linear'}[m])
    axes[0].set_xticks(range(6),[f'CH {ch}' for ch in channels]);axes[0].set(ylabel='Full 20 ms admissions / 96',title='Same primary branch; no target search');axes[0].legend(fontsize=8)
    for label,color in [('quadratic_gain_vs_linear','#246b99'),('quadratic_loss_vs_linear','#a34e45')]:
        axes[1].plot(channels,[summary['by_channel'][str(ch)][label] for ch in channels],'o-',label=label.replace('_',' '),color=color)
    axes[1].set(xlabel='Channel',ylabel='Paired transitions',title='Consistent linear versus quadratic/fallback');axes[1].legend(fontsize=8)
    fig.tight_layout();save(fig,'fullwindow_primary_timing')
    signal=read(HERE/'outcomes/signal.json.gz')['rows'];fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    for db,color in [(-12,'#246b99'),(-24,'#a37b42')]:
        selected=[r for r in signal if r['db']==db and abs(r['timing_error_samples'])==.5]
        axes[0].scatter([r['donor_CFO_error_hz'] for r in selected],[r['evaluation']['quadratic_or_fallback']['cfo_error_hz'] for r in selected],s=20,alpha=.55,label=f'{db}dB',color=color)
    axes[0].axhline(500,color='k',ls='--',lw=.8);axes[0].axhline(-500,color='k',ls='--',lw=.8)
    axes[0].set(xlabel='Earlier CFO prediction error (Hz)',ylabel='Later-bin CFO error (Hz)',title='Frequency information beyond accurate carry');axes[0].legend(fontsize=8)
    strong=[r['evaluation']['quadratic_or_fallback']['cfo_error_hz'] for r in signal if r['db']==-12 and abs(r['timing_error_samples'])==.5]
    axes[1].hist(strong,bins=np.arange(-300,301,25),color='#246b99');axes[1].axvline(-100,color='#a34e45',ls='--');axes[1].axvline(100,color='#a34e45',ls='--')
    axes[1].set(xlabel='Strong primary later CFO error (Hz)',ylabel='Trials',title='0/48 within 100 Hz; grid origin matters')
    accepted=[r for r in rows if r['quadratic_or_fallback_admitted']]
    innovations=[r['quadratic_or_fallback_innovation_hz']/(10_000_000/(44*512)) for r in accepted]
    radius=max(10,int(np.ceil(max(abs(value) for value in innovations))))
    axes[2].hist(innovations,bins=np.arange(-radius-.5,radius+1.5),color='#246b99')
    axes[2].set(xlabel='Natural admitted frequency innovation (bins)',ylabel='Native owners',title='Conditional later-data bin; not donor-posterior precision')
    fig.tight_layout();save(fig,'frequency_innovation_and_grid_origin')
    print(json.dumps(dict(counts=summary['counts'],CH5_8=summary['CH5_8'],innovations=innovation,
        runtime=[summary[k] for k in ['summed_runtime_seconds','native_read_verify_seconds','new_scoring_seconds']],failures=failures),indent=2),flush=True)


if __name__=='__main__':main()
