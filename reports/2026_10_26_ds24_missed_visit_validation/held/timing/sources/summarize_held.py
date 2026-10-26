"""Frozen-method held acquisition transfer and ownership audit, no positions."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;OUT=HERE/'held'
METHODS=['r01_point','r01_search','r02_linear','r02_quadratic','r02_legacy']
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def counts(rows):
    return dict(n=len(rows),original=sum(r['original_pass'] for r in rows),original_export_missing=sum(r['original_missing'] for r in rows),
        methods={m:dict(pilot_confirmations=sum(r[m+'_pilot'] for r in rows),admissions=sum(r[m+'_admitted'] for r in rows),
            new_original_absent=sum(r[m+'_admitted'] and not r['original_pass'] and not r['original_missing'] for r in rows),
            retained_original=sum(r[m+'_admitted'] and r['original_pass'] for r in rows),
            lost_original=sum(not r[m+'_admitted'] and r['original_pass'] for r in rows),
            alternate_pilots=sum(r[m+'_pilot'] and not r[m+'_admitted'] for r in rows),
            additions_only_coverage=sum(r['original_pass'] or (r[m+'_admitted'] and not r['original_missing']) for r in rows)) for m in METHODS})


def main():
    began=time.monotonic();p=read(OUT/'protocol.json');rows=[];execution=[];failures=[];manifests={'r01_search':[],'r02_quadratic':[]}
    sourcecheck=all(sha(path)==h for path,h in p['files'].items());checkpoint=True;selection=True;native=True
    import expansion
    math,adapter=expansion.frozen_modules()
    for case in p['cases']:
        source=OUT/'outcomes'/(case+'.json.gz');data=read(source);readtime=r1time=r2time=0.
        for w in data['rows']:
            checkpoint=checkpoint and read(OUT/'checkpoints'/(w['request_id']+'.json.gz'))==w
            if w['status']!='complete':failures.append(dict(request_id=w['request_id'],error=w.get('error'),cells_completed=len(w['cells'])))
            receipt=w.get('native_receipt',{});readtime+=receipt.get('native_read_verify_seconds',0.)
            native=native and receipt.get('full_reader_exhausted',False) and receipt.get('repeated_blind_acquisition_calls')==0 and receipt.get('fresh_per_window_paired_candidate_parity') is False
            for c in w['cells']:
                value=c['result'];one=value['r01'];two=value['r02'];h=c['header'];original=c['original_fullwindow'];packet=value['r01_packet']
                original_pass=bool(original and any(v['passed_fractional_margin_gate'] for v in original['candidates']))
                row=dict(prediction_id=c['prediction_id'],owner_id=one['owner_id'],case=case,channel=w['channel'],receiver_id=c['receiver_id'],
                    original_pass=original_pass,original_missing=original is None,r01_status=one['status'],r02_status=two['status'],
                    no_donor=one['status']=='no_donor',mode_count=len(packet['modes']),nomination_scores=len(one['exposure']),
                    start_counter=packet['target_support']['start_counter'],stop_counter=packet['target_support']['stop_counter'])
                r1time+=value['r01_scoring_seconds'];r2time+=value['r02_scoring_seconds']
                items={}
                for method,key in [('r01_point','point'),('r01_search','search')]:
                    item=one.get(key);items[method]=item
                    row.update({method+'_pilot':bool(item and item['evaluation']['pilot_confirmed']),
                        method+'_admitted':bool(item and item['evaluation']['admitted']),
                        method+'_margin':item['confirmation'].get('margin') if item else '',
                        method+'_CFO_hz':item['confirmation'].get('tracking_cfo_hz') if item else '',
                        method+'_innovation_hz':item['evaluation'].get('cfo_prediction_residual_hz') if item else ''})
                for method,key in [('r02_linear','linear'),('r02_quadratic','quadratic_or_fallback'),('r02_legacy','legacy_adapter_linear')]:
                    item=two['methods'].get(key);items[method]=item
                    row.update({method+'_pilot':bool(item and item['pilot_confirmed']),method+'_admitted':bool(item and item['admitted']),
                        method+'_margin':item['score'].get('margin') if item else '',method+'_CFO_hz':item['score'].get('tracking_cfo_hz') if item else '',
                        method+'_innovation_hz':item.get('frequency_innovation_hz') if item else ''})
                rows.append(row)
                if one.get('selection_receipt'):
                    r=one['selection_receipt'];copy=dict(r);copy.pop('selection_sha256')
                    saved=read(OUT/'selections'/(c['prediction_id'].replace('/','_')+'.json'))
                    selection=selection and saved==r and math.digest(copy)==r['selection_sha256'] and not r['confirmation_accessed']
                for method in manifests:
                    if not row[method+'_admitted']:continue
                    candidate=dict(prediction_id=c['prediction_id'],owner_id=row['owner_id'],native_observation_id=h.get('native_observation_id'),
                        case=case,channel=w['channel'],receiver_id=c['receiver_id'],visit_index=h['visit_index'],probe_index=h['probe_index'],
                        target_support=packet['target_support'],actual_rf_hz=h['actual_rf_hz'],edge=h['edge'],
                        original_pass=original_pass,original_export_missing=original is None,
                        action='alternative_on_existing_owner' if original_pass else 'newly_confirmed_native_owner',
                        provisional_only=True,no_automatic_replacement=True,independent_added_Doppler_points=0)
                    item=items[method]
                    if method=='r01_search':
                        candidate.update(selected_mode=packet['modes'][item['selected']['mode_index']],
                            selected_offset_samples=item['selected']['score']['offset_samples'],nomination=item['selected']['score'],confirmation=item['confirmation'],
                            native_search_blocks=item['native_search_blocks'],native_confirmation_blocks=item['native_confirmation_blocks'],
                            selection_receipt_sha256=one['selection_receipt']['selection_sha256'],support_class='donor_continuity_compatible')
                    else:candidate.update(donors=two['donors'],point=item['point'],score=item['score'],frequency_innovation_hz=item['frequency_innovation_hz'])
                    manifests[method].append(candidate)
        execution.append(dict(case=case,seconds=data['seconds'],paired_windows=len(data['rows']),read_verify_seconds=readtime,
            R01_scoring_seconds=r1time,R02_scoring_seconds=r2time,source_sha256=sha(source)))
    innovation={}
    for m in METHODS:
        x=[r[m+'_innovation_hz'] for r in rows if r[m+'_admitted']]
        innovation[m]=dict(n=len(x),zero_bins=sum(abs(v)<1e-6 for v in x),nonzero_bins=sum(abs(v)>=1e-6 for v in x),
            maximum_absolute_hz=max(abs(v) for v in x) if x else None)
    summary=dict(schema='held-frozen-method-acquisition-transfer/v1',requested_windows=288,requested_cells=576,observed_cells=len(rows),
        unique_native_owners=len({r['owner_id'] for r in rows}),counts=counts(rows),CH5_8=counts([r for r in rows if r['channel']>=5]),
        by_case={case:counts([r for r in rows if r['case']==case]) for case in p['cases']},
        by_channel={str(ch):counts([r for r in rows if r['channel']==ch]) for ch in [1,4,5,6,7,8]},
        by_channel_receiver={f'CH{ch}/RX{rx}':counts([r for r in rows if r['channel']==ch and r['receiver_id']==rx]) for ch in [1,4,5,6,7,8] for rx in [0,1]},
        no_donor_cells=sum(r['no_donor'] for r in rows),innovations=innovation,execution=execution,failed_windows=failures,
        all_bound_hashes_unchanged=sourcecheck,all_checkpoints=bool(checkpoint),all_selection_receipts=bool(selection),
        all_native_read_receipts=bool(native),methods_never_combined=True,no_target_retune=True,no_recovered_donors=True,
        reused_global_parity=True,fresh_per_window_blind_parity=False,independent_added_Doppler_points=0,position_ready=False,
        held_from_revision_development=True,previously_exposed_to_other_studies=True,protocol_sha256=sha(OUT/'protocol.json'),
        summary_seconds=time.monotonic()-began)
    write(OUT/'summary.json',summary)
    with (OUT/'cells.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    for method,candidates in manifests.items():write(OUT/(method+'_candidate_manifest.json'),dict(method=method,candidates=candidates,
        no_method_union=True,provisional=True,no_new_independent_points_admitted=True,position_ready=False))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(13,4));channels=[1,4,5,6,7,8]
    colors=['#999999','#777777','#246b99','#2c8b68'];labels=['Original full 20 ms','R01 point admissions','R01 search admissions','R02 quadratic admissions']
    for j,(key,color,label) in enumerate(zip(['original','r01_point','r01_search','r02_quadratic'],colors,labels)):
        vals=[summary['by_channel'][str(ch)]['original'] if key=='original' else summary['by_channel'][str(ch)]['methods'][key]['admissions'] for ch in channels]
        axes[0].bar(np.arange(6)+(j-1.5)*.18,vals,width=.17,color=color,label=label)
    axes[0].set_xticks(range(6),[f'CH {ch}' for ch in channels]);axes[0].set(ylabel='Held native owners / 96 per channel',title='Frozen methods; sample exposures differ');axes[0].legend(fontsize=8)
    for j,(key,color,label) in enumerate([('r01_search','#246b99','R01 search'),('r02_quadratic','#2c8b68','R02 quadratic / fallback')]):
        axes[1].bar(np.arange(6)+(j-.5)*.3,[summary['by_channel'][str(ch)]['methods'][key]['new_original_absent'] for ch in channels],width=.28,color=color,label=label)
    axes[1].set_xticks(range(6),[f'CH {ch}' for ch in channels]);axes[1].set(ylabel='New original-absent admissions',title='Separate additions only; no best-method union');axes[1].legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'held_acquisition_transfer.png',dpi=170,bbox_inches='tight');fig.savefig(OUT/'held_acquisition_transfer.pdf',bbox_inches='tight');plt.close(fig)
    print(json.dumps(dict(counts=summary['counts'],CH5_8=summary['CH5_8'],no_donor=summary['no_donor_cells'],
        innovations=innovation,failures=failures,seconds=[e['seconds'] for e in execution]),indent=2),flush=True)


if __name__=='__main__':main()
