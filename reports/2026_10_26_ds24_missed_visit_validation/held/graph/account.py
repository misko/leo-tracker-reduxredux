"""Separately account held R01/R02 additions through the unchanged RF graph."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
HELD=Path('/srv/bulk/leo/research/ds24-missed-visit-r02/timing/held')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
sys.path.insert(0,str(R01/'validation'))
from baseline_scope import metadata_inventory,sha,observation_id
from prepare_overlay import rebuild_graph
from integration import digest
METHODS=('r01_search','r02_quadratic')


def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def binding(candidate,tracking,inventory,original,method):
    support=candidate['target_support'];rx=candidate['receiver_id']
    n=next(n for n in inventory if n['native_receiver_id']==rx and n['start_counter']==support['start_counter'])
    oid=n['observation_id'];assert oid==observation_id(tracking['source']['session_id'],rx,support['start_counter'])
    assert support['stop_counter']==n['stop_counter'] and support['source_id']==n['recording_id']
    assert support['stream_generation']==n['stream_generation']
    assert support['raw_recording_authority_digest']==n['raw_authority_digest'] and support['source_input_sha256']==n['source_input_sha256']
    assert support['tracking_sha256']==sha(SOURCE/candidate['case']/'tracking.json')
    assert candidate['owner_id']==f"{n['recording_id']}/rx{rx}/{n['start_counter']}:{n['stop_counter']}"
    assert candidate['channel']==n['channel'] and candidate['actual_rf_hz']==n['actual_rf_hz'] and candidate['edge']==n['edge']
    assert candidate['visit_index']==n['visit_index'] and candidate['probe_index']==n['probe_index']
    assert candidate['native_observation_id'] in (None,oid)
    assert candidate['original_pass']==(oid in {o['observation_id'] for o in original})
    assert not candidate['original_export_missing']
    score=candidate['confirmation'] if method=='r01_search' else candidate['score']
    point=candidate['selected_mode'] if method=='r01_search' else candidate['point']
    assert score['status']=='complete' and score['margin']>=.025
    assert abs(score['tracking_cfo_hz']-point['cfo_hz'])<=point['cfo_half_width_hz']
    donors=candidate['selected_mode']['donors'] if method=='r01_search' else candidate['donors']
    for donor in donors:
        dn=next(n for n in inventory if n['native_receiver_id']==rx and n['start_counter']==donor['start_counter'])
        assert donor['stop_counter']==dn['stop_counter']<=n['start_counter']
        assert donor['generation']==support['native_generation']
        assert all(dn[k]==n[k] for k in ('recording_id','stream_generation','raw_authority_digest','channel','edge','actual_rf_hz','sample_rate_hz'))
    return dict(prediction_id=candidate['prediction_id'],native=n,
        measurement=dict(measured_cfo_hz=score['tracking_cfo_hz'],fractional_margin=score['margin']),
        original_owner=candidate['original_pass'],
        producer_native_ID_was_null=candidate['native_observation_id'] is None,
        identity_authority='standard session:RX:start SHA256 binding independently verified against immutable native tracking inventory',
        frequency_innovation_hz=score['tracking_cfo_hz']-point['cfo_hz'])


def stage(original,candidates):
    rows=copy.deepcopy(original);ids={o['observation_id'] for o in original}
    for candidate in candidates:
        n=candidate['native'];assert n['observation_id'] not in ids;ids.add(n['observation_id'])
        rows.append(dict({k:n[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')},**candidate['measurement']))
    assert rows[:len(original)]==original
    return rows


def prepare():
    held=read(HELD/'protocol.json');summary=read(HELD/'summary.json');cases=read(R01/'split.json')['validation']
    assert held['cases']==cases and summary['protocol_sha256']==sha(HELD/'protocol.json')
    assert all(summary[k] for k in ('all_bound_hashes_unchanged','all_checkpoints','all_selection_receipts','all_native_read_receipts'))
    for path,h in held['files'].items():assert sha(path)==h,path
    prior=read(R01/'validation/baseline_source_receipt.json')['files_sha256']
    scientific=[REPO/'tools/evaluate_ds22_public_tracks.py',REPO/'tools/evaluate_ds22_merged_tracks.py',
        REPO/'src/leo/analysis/graph_tracklets.py',REPO/'src/leo/analysis/polynomial_tracklets.py',
        REPO/'tools/localize_merged_track_catalogue.py',REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json']
    for path in scientific:assert sha(path)==prior[str(path)],path
    jobs=[];failures=[];input_hashes={str(HELD/'protocol.json'):sha(HELD/'protocol.json'),str(HELD/'summary.json'):sha(HELD/'summary.json')}
    inventories={case:metadata_inventory(case) for case in cases}
    for case in cases:
        for name in ('observations.json','tracking.json'):input_hashes[str(SOURCE/case/name)]=sha(SOURCE/case/name)
    for method in METHODS:
        path=HELD/(method+'_candidate_manifest.json');manifest=read(path);input_hashes[str(path)]=sha(path)
        assert manifest['method']==method and manifest['no_method_union']
        by_case={case:[] for case in cases};seen=set()
        for candidate in manifest['candidates']:
            try:
                bound=binding(candidate,*inventories[candidate['case']],method)
                oid=bound['native']['observation_id'];assert oid not in seen;seen.add(oid)
                if not bound['original_owner']:by_case[candidate['case']].append(bound)
            except Exception as exc:
                failures.append(dict(method=method,prediction_id=candidate['prediction_id'],error=repr(exc)))
        for case in cases:
            output=HERE/'jobs'/method/(case+'.json')
            job=dict(case=case,method=method,candidates=by_case[case],
                original_observations_sha256=sha(SOURCE/case/'observations.json'),
                tracking_sha256=sha(SOURCE/case/'tracking.json'))
            write(output,job);input_hashes[str(output)]=sha(output);jobs.append(dict(case=case,method=method))
    source_hashes={str(path):sha(path) for path in scientific+[R01/'validation/prepare_overlay.py',R01/'validation/baseline_scope.py',Path(__file__),HERE/'test_account.py']}
    write(HERE/'protocol.json',dict(schema='held-separate-additions-RF-graph-accounting/v1',jobs=jobs,input_hashes=input_hashes,source_hashes=source_hashes,
        native_provenance_failures=failures,maximum_workers=2,per_case_method_cap_seconds=120,BLAS_threads=1,
        no_IQ_reads=True,no_satellite_search=True,no_position_jobs=True,no_method_union=True,original_measurements_preserved=True,
        unchanged_original_graph_and_raw_curvature_gates=True,authorization='Root held graph accounting request under HELD_VALIDATION_PLAN',
        plan_sha256=sha(R01/'HELD_VALIDATION_PLAN.md')))
    print(dict(jobs=len(jobs),provenance_failures=failures,new_by_method={m:sum(len(read(HERE/'jobs'/m/(c+'.json'))['candidates']) for c in cases) for m in METHODS}),flush=True)


def worker(case,method):
    assert all(os.environ.get(k)=='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120second held graph cap')));signal.alarm(120)
    began=time.monotonic();job=read(HERE/'jobs'/method/(case+'.json'));original=read(SOURCE/case/'observations.json')
    assert sha(SOURCE/case/'observations.json')==job['original_observations_sha256']
    rows=stage(original,job['candidates']);new={c['native']['observation_id'] for c in job['candidates']}
    config=read(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
    tracks,g=rebuild_graph(rows,case,config);ids={oid for t in tracks for oid in t['observation_ids']};curved=set(g['curved_observation_ids'])
    result=dict(case=case,method=method,status='complete',new_native=len(new),new_in_graph=len(new&ids),
        new_curved=len(new&curved),new_outside_graph=len(new-ids),
        new_graph_ids=sorted(new&ids),new_curved_ids=sorted(new&curved),new_outside_graph_ids=sorted(new-ids),
        new_CH58=sum(c['native']['channel']>=5 for c in job['candidates']),
        new_CH58_curved=sum(c['native']['channel']>=5 and c['native']['observation_id'] in curved for c in job['candidates']),
        original_GLRT_count=len(original),total_GLRT_count=len(rows),original_rows_and_margins_exact=True,
        observations_digest=digest(rows),tracks_digest=digest(tracks),
        graph_tracks=g['graph_tracks'],curved_tracks=g['curved_tracks'],
        native_IDs_derived_from_verified_authority=True,no_IQ_reads=True,no_satellite_or_position_inference=True,
        seconds=time.monotonic()-began)
    folder=HERE/'graphs'/method/case;folder.mkdir(parents=True,exist_ok=False)
    write(folder/'observations.json',rows);write(folder/'tracks.json',tracks);write(folder/'audit.json',result)
    print(dict(case=case,method=method,new=result['new_native'],graph=result['new_in_graph'],curved=result['new_curved'],outside=result['new_outside_graph']),flush=True)


def dispatch(job):
    log=HERE/'logs'/(job['method']+'-'+job['case']+'.log');log.parent.mkdir(exist_ok=True)
    with log.open('x') as f:
        result=subprocess.run([sys.executable,'-B',str(Path(__file__)),'worker','--case',job['case'],'--method',job['method']],stdout=f,stderr=subprocess.STDOUT,timeout=125)
    return dict(job,returncode=result.returncode)


def run():
    assert os.getuid()==1000
    p=read(HERE/'protocol.json')
    # Original manifests need privileged preflight hashes; all graph inputs and
    # sources below are public metadata and readable under the numeric user.
    for path,h in dict(p['input_hashes'],**p['source_hashes']).items():assert sha(path)==h,path
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(dispatch,j) for j in p['jobs']]):results.append(future.result())
    cases=[]
    for result in results:
        path=HERE/'graphs'/result['method']/result['case']/'audit.json'
        cases.append(read(path) if result['returncode']==0 else dict(result,status='failed'))
    cases.sort(key=lambda r:(r['method'],r['case']));totals={}
    for method in METHODS:
        selected=[r for r in cases if r['method']==method and r['status']=='complete']
        totals[method]={k:sum(r[k] for r in selected) for k in ('new_native','new_in_graph','new_curved','new_outside_graph','new_CH58','new_CH58_curved')}
    write(HERE/'summary.json',dict(schema='held-separate-RF-graph-accounting/v1',cases=cases,totals=totals,
        all_complete=all(r['status']=='complete' for r in cases),native_provenance_failures=p['native_provenance_failures'],
        no_method_union=True,no_new_IQ_reads=True,no_satellite_search=True,no_position_jobs=True,
        graph_qualification_is_not_satellite_association=True,protocol_sha256=sha(HERE/'protocol.json')))
    print(json.dumps(totals,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run','worker']);parser.add_argument('--case');parser.add_argument('--method',choices=METHODS);a=parser.parse_args()
    if a.action=='worker':worker(a.case,a.method)
    else:{'prepare':prepare,'run':run}[a.action]()
