"""All24 application of frozen RF nomination and original-history R01 ports."""
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
R01 = Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
R02 = Path('/srv/bulk/leo/research/ds24-missed-visit-r02')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
PRED = R01/'expansion/prediction'
HELD = R02/'validation/held_graph'
RAW = HERE/'raw'

def read(path):
    import gzip
    with (gzip.open(path, 'rt') if str(path).endswith('.gz') else Path(path).open()) as f:
        return json.load(f)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    import gzip
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with (gzip.open(path, 'xt') if str(path).endswith('.gz') else path.open('x')) as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n')

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

def ports():
    sys.path.insert(0, str(PRED))
    base = module('original_coherent_application', PRED/'study.py')
    return base, base.ports(), module('original_RF_selector', PRED/'selection.py')

def cohort():
    split = read(R01/'split.json')
    return split, split['validation'] + split['development']

def nomination(case, held, select):
    if held:
        lp = HELD/'jobs/r01_search'/(case+'.json')
        gp = HELD/'graphs/r01_search'/case/'audit.json'
        job = read(lp); graph = read(gp)
        assert graph['no_satellite_or_position_inference'] and graph['original_rows_and_margins_exact']
        ledger = dict(case=case, staged=[dict(status='new_native_exploratory_addition',
            existing_owner=c['original_owner'], channel=c['native']['channel'],
            native_receiver_id=c['native']['native_receiver_id'],
            target_observation_id=c['native']['observation_id'], native=c['native'])
            for c in job['candidates']])
        curved = graph['new_curved_ids']
    else:
        lp = R01/'validation'/(case+'_additions.json')
        gp = R01/'validation'/(case+'-additions-r01')/'graph_audit.json'
        ledger = read(lp)
        if gp.exists():
            graph = read(gp); assert graph['new_GPS_or_satellite_identity_used'] is False
            curved = graph['graph']['curved_observation_ids']
        else:
            assert not ledger['staged'], 'missing graph with nomination candidates'
            curved = []
    return select.lanes(ledger, set(curved)), [lp]+([gp] if gp.exists() else [])

def nominate():
    split, cases = cohort(); base, port, select = ports()
    files = {str(p):sha(p) for p in [ROOT/'PLAN.md', R01/'split.json',
        Path(__file__), PRED/'selection.py', PRED/'study.py',
        R01/'prediction/predictor.py', R01/'prediction/handoff.py',
        R01/'prediction/study.py', R01/'validation/baseline_scope.py', base.MAPPER]}
    blocks=[]; rows=[]; pairs=[]
    for case in cases:
        lanes, inputs = nomination(case, case in split['validation'], select)
        track = SOURCE/case/'tracking.json'; data=read(track)
        assert data['source']['sample_rate_hz']==10000000 and data['source']['probe_ms']==20
        chosen=[select.nominate(lane, data['source']['probes'], 10000000) for lane in lanes[:2]]
        selected=select.deduplicate(chosen)  # Original per-application bound, applied per case.
        assert len(chosen)<=2 and len(selected)<=160
        blocks.extend(chosen);pairs.extend(selected)
        rows.append(dict(case=case, cohort='reserved' if case in split['validation'] else 'development',
            eligible_lanes=len(lanes), selected_lanes=len(chosen), paired_windows=len(selected),
            status='eligible' if chosen else 'baseline_no_eligible_curved_CH58_lane',
            capped_blocks=sum(b['capped'] for b in chosen), ranked_lanes=lanes))
        files.update({str(p):sha(p) for p in inputs+[track,SOURCE/case/'observations.json']})
    write(HERE/'nominations.json', dict(cases=rows, unavailable=[r for r in split['rows'] if not r['available']],
        blocks=blocks, paired_windows=len(pairs), receiver_cells=2*len(pairs),
        source_inputs=files, raw_IQ_reads=0, geographic_inputs=False,
        rule='exact original RF selector per case, top2; original cap80/block before dedup'))
    write(HERE/'nominated_pairs.json', pairs)
    print(json.dumps([{k:r[k] for k in ('case','eligible_lanes','selected_lanes','paired_windows','capped_blocks')} for r in rows]), flush=True)

def prepare():
    began=time.monotonic(); split,cases=cohort(); base,port,select=ports()
    nominations=read(HERE/'nominations.json'); files=dict(nominations['source_inputs'])
    for path,h in files.items(): assert sha(path)==h,path
    old=read(R01/'prediction/panel.json'); held=read(R02/'held_validation/prediction/panel.json') if (R02/'held_validation/prediction/panel.json').exists() else None
    # Native session authority is the persisted tracking source, exactly as original study.prepare.
    slots=[]; documents={}
    old_pairs={(s['case'],s['probe_metadata']['visit_index']) for s in old['slots']}
    for item in read(HERE/'nominated_pairs.json'):
        case=item['case'];probe=item['probe']
        if case not in documents: documents[case]=read(SOURCE/case/'tracking.json')
        data=documents[case]; source=data['source']; probes=source['probes']
        track=SOURCE/case/'tracking.json'; inp=Path('/srv/bulk/leo/fast-scan-inputs')/(source['session_id']+'.json')
        files[str(inp)]=sha(inp)
        slot=dict(request_id=f"{case}-CH{probe['channel']}-V{probe['visit_index']}-EXP", case=case,
            channel=probe['channel'],block_ids=item['block_ids'],status='nominated',
            tracking=dict(path=str(track),sha256=sha(track)),source_input=dict(path=str(inp),sha256='sha256:'+sha(inp)),
            probe_metadata=probe,probe=dict(probe,duration_samples=200000,window_start_counter=probe['valid_start_counter']),
            sample_rate_hz=10000000,cells=[],overlaps_original_sparse_panel=(case,probe['visit_index']) in old_pairs)
        try:slot['raw_authority']=port['mapper'].one(port['panel'].request(slot,probe))
        except Exception as exc:slot.update(status='missing',error=repr(exc))
        for rx in [0,1]:
            n=port['native'].native_row(data,dict(probe,receiver_id=rx),[0,1])
            h=dict(prediction_id=f"{slot['request_id']}/RX{rx}",request_id=slot['request_id'],case=case,
                channel=probe['channel'],receiver_id=rx,edge=probe['edge'],sample_rate_hz=10000000,
                window_samples=200000,start_counter=probe['valid_start_counter'],stop_counter=probe['valid_start_counter']+200000,
                visit_index=probe['visit_index'],probe_index=probe['probe_index'],generation=source['stream_generation'],
                source_id=source['session_id'],actual_rf_hz=probe['actual_rf_hz'],tracking_sha256=slot['tracking']['sha256'],
                raw_recording_authority_digest=source['raw_recording_authority_digest'],native_observation_id=n['observation_id'])
            same=[p for p in probes if p['channel']==probe['channel'] and p['edge']==probe['edge'] and p['receiver_id']==rx]
            history=sorted([p for p in same if p['valid_start_counter']+200000<=h['start_counter'] and
                0<(h['start_counter']-p['valid_start_counter'])/10000000<=port['predictor'].HORIZON_S],
                key=lambda p:p['valid_start_counter'])[-port['predictor'].HISTORY_VISITS:]
            slot['cells'].append(dict(header=h,history=history,processed_probe_present=any(p['visit_index']==probe['visit_index'] for p in same)))
        slots.append(slot)
    write(HERE/'panel.json',dict(cases=cases,slots=slots,paired_windows=len(slots),receiver_cells=2*len(slots),raw_IQ_reads=0))
    rows=[];history={};by_id={s['request_id']:s for s in slots}
    for slot in slots:
        for cell in slot['cells']:
            h=cell['header'];row=dict(header=h,status='complete',forecast=port['predictor'].predict(h,cell['history']))
            rows.append(row)
            for p in cell['history']:history[h['case'],p['visit_index']]=p
    write(HERE/'predictions.json',dict(rows=rows,raw_IQ_reads=0))
    # The persisted JSON reload is the original R01 v2 alias-isolation boundary.
    rows=read(HERE/'predictions.json')['rows']; unique={}
    for row in rows:
        for mode in row['forecast'].get('modes',[]):
            for d in mode['donors']:unique.setdefault((row['header']['case'],d['visit_index']),row['header']['request_id'])
    authority=[];lookup={}
    for (case,visit),rid in sorted(unique.items()):
        item=dict(case=case,visit_index=visit,status='metadata_verified')
        try:
            a=port['mapper'].one(port['panel'].request(by_id[rid],history[case,visit]));lookup[case,visit]=a;item['raw_authority']=a
        except Exception as exc:item.update(status='failed',error=repr(exc))
        authority.append(item)
    write(HERE/'donor_authority.json',dict(rows=authority,raw_IQ_reads=0));packets=[]
    for row in rows:
        slot=by_id[row['header']['request_id']]
        packet=port['handoff'].enrich(json.loads(json.dumps(row,allow_nan=False)),slot,lookup) if slot['status']=='nominated' else dict(row,donor_metadata_status='target_metadata_unavailable')
        packet.update(block_ids=slot['block_ids'],overlaps_original_sparse_panel=slot['overlaps_original_sparse_panel']);packets.append(packet)
    write(HERE/'prediction_packets_v2.json',dict(rows=packets,raw_IQ_reads=0,metadata_handoff_version=2))
    failures=[]
    for slot in slots:
        if slot['status']!='nominated':failures.append(dict(request_id=slot['request_id'],error=slot.get('error')))
        else:
            a=slot['raw_authority'];files[a['index_path']]=sha(a['index_path'])
            assert 'sha256:'+files[a['index_path']]==a['index_sha256']
    for p in packets:
        if p['donor_metadata_status']!='verified':failures.append(dict(prediction_id=p['header']['prediction_id'],metadata_status=p['donor_metadata_status']))
        else:
            h=p['header'];slot=by_id[h['request_id']];acq=slot['raw_authority']['index']['acquisition']
            assert h['generation']==acq['generation'] and h['stream_generation']==slot['cells'][h['receiver_id']]['header']['generation']
            for mode in p['forecast'].get('modes',[]):
                for d in mode['donors']:
                    assert d['support']['stop_counter']<=h['start_counter'] and d['stream_generation']==h['stream_generation']
    write(HERE/'metadata_audit.json',dict(all_passed=not failures,failures=failures,raw_IQ_reads=0,
        target_windows=len(slots),donor_windows=len(authority),serialized_v2_boundary=True,seconds=time.monotonic()-began))
    files.update({str(HERE/n):sha(HERE/n) for n in ['nominations.json','nominated_pairs.json','panel.json','predictions.json','prediction_packets_v2.json','donor_authority.json','metadata_audit.json','test_application.py']})
    write(HERE/'forecast_protocol.json',dict(files=files,raw_IQ_reads=0,geography_inputs=False,metadata_handoff_version=2,
        no_recovered_donor_feedback=True,cases=cases,paired_windows=len(slots)))
    print(dict(paired_windows=len(slots),metadata_failures=len(failures),seconds=time.monotonic()-began),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['nominate','prepare']);args=parser.parse_args()
    globals()[args.action]()
