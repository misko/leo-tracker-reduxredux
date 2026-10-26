"""Exact-R01 coherent application handoff and offline acquisition audit."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent;OUT=HERE/'expansion_v2'
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def passes(result,method,key='admitted'):return bool(result.get(method) and result[method]['evaluation'][key])
def counts(rows):
    return dict(n=len(rows),original=sum(r['original_pass'] for r in rows),point=sum(r['point_admitted'] for r in rows),
        search=sum(r['search_admitted'] for r in rows),pilot=sum(r['search_pilot'] for r in rows),
        new=sum(r['search_admitted'] and not r['original_pass'] for r in rows),
        alternate_pilot=sum(r['search_pilot'] and not r['search_admitted'] for r in rows),
        no_donor=sum(r['status']=='no_donor' for r in rows),
        retained_original=sum(r['search_admitted'] and r['original_pass'] for r in rows),
        lost_original=sum(not r['search_admitted'] and r['original_pass'] for r in rows))


def main():
    began=time.monotonic();p=read(OUT/'protocol.json');rows=[];candidates=[];execution=[];failures=[];receipts=True;selection=True;disjoint=True
    panel=read(p['panel_path']);slots={s['request_id']:s for s in panel['slots']}
    import expansion
    math,adapter=expansion.frozen_modules()
    old_owners=set()
    for case in p['cases']:
        for w in read(expansion.R01/'timing/outcomes'/(case+'.json.gz'))['rows']:
            old_owners.update(c['result']['owner_id'] for c in w['cells'])
        source=OUT/'outcomes'/(case+'.json.gz');data=read(source);readtime=scoretime=0.
        for w in data['rows']:
            checkpoint=read(OUT/'checkpoints'/(w['request_id']+'.json.gz'));receipts=receipts and checkpoint==w
            if w['status']!='complete':failures.append(dict(request_id=w['request_id'],error=w.get('error')))
            native=w.get('native_receipt',{});readtime+=native.get('native_read_verify_seconds',0.)
            receipts=receipts and native.get('full_reader_exhausted',False) and native.get('repeated_blind_acquisition_calls')==0 and native.get('fresh_per_window_paired_candidate_parity') is False
            for c in w['cells']:
                r=c['result'];packet=c['packet'];h=packet['header'];scoretime+=c['scoring_seconds'];s=r.get('search');point=r.get('point')
                original=c['original_fullwindow'] or {};orig=any(v['passed_fractional_margin_gate'] for v in original.get('candidates',[]))
                row=dict(prediction_id=c['prediction_id'],request_id=w['request_id'],case=case,channel=w['channel'],receiver_id=c['receiver_id'],
                    owner_id=r['owner_id'],native_observation_id=h.get('native_observation_id'),status=r['status'],
                    original_pass=orig,point_admitted=passes(r,'point'),search_admitted=passes(r,'search'),search_pilot=passes(r,'search','pilot_confirmed'),
                    sparse_overlap=r['owner_id'] in old_owners,mode_count=len(packet['modes']),nomination_scores=len(r['exposure']),
                    selected_mode=s['selected']['mode_index'] if s else '',offset_samples=s['selected']['score']['offset_samples'] if s else '',
                    confirmation_margin=s['confirmation'].get('margin') if s else '',CFO_hz=s['confirmation'].get('tracking_cfo_hz') if s else '',
                    start_counter=packet['target_support']['start_counter'],stop_counter=packet['target_support']['stop_counter'])
                rows.append(row)
                if s:
                    receipt=r['selection_receipt'];copy=dict(receipt);copy.pop('selection_sha256')
                    saved=read(OUT/'selections'/(c['prediction_id'].replace('/','_')+'.json'))
                    selection=selection and receipt==saved and math.digest(copy)==receipt['selection_sha256'] and not receipt['confirmation_accessed']
                    for group,blocks in [('search',s['native_search_blocks']),('confirmation',s['native_confirmation_blocks'])]:
                        disjoint=disjoint and all(any(i['group']==group and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in r['ownership']['intervals']) for b in blocks)
                    if passes(r,'search','pilot_confirmed'):
                        mode=packet['modes'][s['selected']['mode_index']]
                        candidates.append(dict(prediction_id=c['prediction_id'],owner_id=r['owner_id'],native_observation_id=h.get('native_observation_id'),
                            case=case,channel=w['channel'],receiver_id=c['receiver_id'],visit_index=h['visit_index'],probe_index=h['probe_index'],
                            actual_rf_hz=h['actual_rf_hz'],edge=h['edge'],target_support=packet['target_support'],selected_mode=mode,
                            selected_offset_samples=s['selected']['score']['offset_samples'],nomination=s['selected']['score'],confirmation=s['confirmation'],
                            native_search_blocks=s['native_search_blocks'],native_confirmation_blocks=s['native_confirmation_blocks'],
                            block_coordinate_system='native sample offsets relative to target start, including interpolation guards',
                            confirmation_native_support=[dict(start_counter=packet['target_support']['start_counter']+b['sample_start'],
                                stop_counter=packet['target_support']['start_counter']+b['sample_stop'],generation=packet['target_support']['native_generation']) for b in s['native_confirmation_blocks']],
                            support_class='donor_continuity_compatible' if passes(r,'search') else 'alternate_pilot_discovery',original_pass=orig,
                            action='alternative_on_existing_owner' if orig else 'newly_confirmed_native_owner',sparse_overlap=row['sparse_overlap'],
                            selection_receipt_sha256=receipt['selection_sha256'],block_ids=slots[w['request_id']]['block_ids'],
                            no_automatic_replacement=True,provisional_only=True,uncertainty_weights_qualified=False))
        execution.append(dict(case=case,seconds=data['seconds'],paired_windows=len(data['rows']),read_verify_seconds=readtime,
            scoring_seconds=scoretime,source_sha256=sha(source)))
    summary=dict(schema='R01-coherent-application-summary/v2',paired_windows=sum(e['paired_windows'] for e in execution),receiver_cells=len(rows),
        counts=counts(rows),by_case={c:counts([r for r in rows if r['case']==c]) for c in p['cases']},
        by_channel_receiver={f'{c}/CH{ch}/RX{rx}':counts([r for r in rows if r['case']==c and r['channel']==ch and r['receiver_id']==rx])
            for c in p['cases'] for ch in sorted({r['channel'] for r in rows if r['case']==c}) for rx in [0,1]},
        sparse_overlap_cells=sum(r['sparse_overlap'] for r in rows),new_outside_sparse=sum(r['search_admitted'] and not r['original_pass'] and not r['sparse_overlap'] for r in rows),
        execution=execution,failed_windows=failures,all_native_receipts_and_checkpoints_valid=bool(receipts),
        all_selection_receipts_valid=bool(selection),selected_sample_groups_disjoint=bool(disjoint),
        exact_R01_policy=True,no_new_recovered_donors=True,fresh_per_window_blind_parity=False,
        ready_for_coherence_and_causal_association=True,position_ready=False,independent_added_Doppler_points=0,
        protocol_sha256=sha(OUT/'protocol.json'),summary_seconds=time.monotonic()-began)
    write(OUT/'summary.json',summary)
    with (OUT/'cells.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(OUT/'candidate_manifest.json',dict(schema='timing-development-candidates/v1',candidates=candidates,
        exact_R01_coherent_application=True,source_protocol_sha256=sha(OUT/'protocol.json'),
        provisional=True,ready_for_position=False,no_new_independent_points_admitted=True))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
