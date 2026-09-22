"""Read-only selection of a counter-contiguous dual-RX GLRT example."""
import hashlib
import json
from pathlib import Path
import statistics
import zstandard
import report_glrt_phase_segment_comparison as legacy
from leo.analysis.starlink.kalman_tracking import canonical_digest
from leo.storage import RecordingStore, PinnedLocalRoot

SESSION='cap-20260825T010019-89c2889553e0'
RUN='capture-34471d9087a94ec1b043951350de3956'
ROOT=Path('/srv/bulk/leo')
PATH=ROOT/'recordings/2026/08/25'/SESSION
branches=['sha256:be34d146cfec9d9fe8b1fd1a73e2dd2c0fa6cc3931eed839f24d8539bcaae69d','sha256:5f2716dd54e070caeac4cc1ea76b694bdea81a4694d9b70d25432e84b238e856']

def main():
    manifest=json.loads((PATH/'manifest.json').read_bytes())
    stream=next(s for s in manifest['streams'] if s['stream_id']=='stream-1')
    compressed=(PATH/stream['timeline_relative_path']).read_bytes()
    assert 'sha256:'+hashlib.sha256(compressed).hexdigest()==stream['timeline_sha256']
    with zstandard.ZstdDecompressor().stream_reader(compressed) as f:
        rows=[json.loads(line) for line in f.read().splitlines()]
    assert all(r['device_sample_counter'] is not None for r in rows)
    assert all(b['device_sample_counter']==a['device_sample_counter']+a['sample_count'] for a,b in zip(rows,rows[1:]))
    assert sum(r['sample_count'] for r in rows)==150000000
    c=stream['continuity']
    assert c['sample_loss_observable'] and c['device_span_sample_count']==150000000
    assert c['gap_count']==c['missing_sample_count']==c['overflow_count']==c['enqueue_failure_count']==0
    _,paths=legacy.load_path_evidence(ROOT,SESSION,RUN)
    tracks=legacy.deduplicate_glrt_tracks(paths)
    selected=[next(t for t in tracks if t.branch_id==branch) for branch in branches]
    lo=max(t.start_s for t in selected);hi=min(t.end_s for t in selected)
    detections=[]
    for rx,t in enumerate(selected):
        canonical={o.observation_id:o for o in t.evidence.dealiased_bank.observations}
        sources={s for oid in t.track.observation_ids for s in canonical[oid].source_observation_ids}
        found={}
        for d in t.evidence.pilot_scan['detections']:
            n=d['sample_start'];time=n/2500000
            if not lo<=time<=hi:continue
            scores=[(candidate,next(s for s in candidate['scores'] if s['method']=='glrt64')) for candidate in d['candidates'] if canonical_digest(dict(sample_start=n,candidate_rank=candidate['rank'],method='glrt64')) in sources]
            if scores:
                candidate,score=max(scores,key=lambda p:p[1]['margin'])
                found[n]=dict(rx=rx,time_s=time,candidate_rank=candidate['rank'],**score)
        detections.append(found)
    common=sorted(set(detections[0])&set(detections[1]))
    choices=[]
    for n in common:
        grid=[k for k in common if n<=k<n+2500000]
        if n/2500000+1<=hi and len(grid)>=20:
            quality=min(detections[rx][k]['margin'] for rx in (0,1) for k in grid)
            choices.append((len(grid),quality,n,grid))
    count,quality,start,grid=max(choices)
    scores=[detections[rx][k] for rx in (0,1) for k in grid]
    store=RecordingStore.open_pinned(PinnedLocalRoot(ROOT))
    try:
        bundle=store.inspect(SESSION)
        raw=store.reader(bundle,'stream-1',verify=True).read(start,2500000,receiver_ids=(0,1))
    finally:store.close()
    result=dict(session=SESSION,run=RUN,stream='stream-1',radio=stream['radio'],continuity=c,
        manifest_sha256=hashlib.sha256((PATH/'manifest.json').read_bytes()).hexdigest(),timeline_sha256=stream['timeline_sha256'],
        counter_boundaries_verified=len(rows)-1,duty_percent=100,interval_s=[start/2500000,start/2500000+1],
        raw_shape=list(raw.shape),raw_slice_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
        selection='First historical post-fix inventory entry; stream-1 paired branches from its published screen; select 1 s maximizing paired associated probe count, then minimum GLRT margin; ties choose latest. Missing associations are not capture gaps.',
        branch_overlap_s=[lo,hi],branches=branches,source_products={t.scope:t.evidence.source_digests for t in selected},scores=scores,
        summaries=[dict(rx=rx,probes=len(grid),median_exact=statistics.median(r['exact_score'] for r in scores if r['rx']==rx),minimum_exact=min(r['exact_score'] for r in scores if r['rx']==rx),median_control=statistics.median(r['control_score'] for r in scores if r['rx']==rx),minimum_margin=min(r['margin'] for r in scores if r['rx']==rx)) for rx in (0,1)])
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
