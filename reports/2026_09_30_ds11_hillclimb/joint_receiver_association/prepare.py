"""Bind original DS11 tracks to complete paired detection opportunities."""
import hashlib
import inspect
import json
from collections import defaultdict,Counter
from pathlib import Path
import sys
import time
from ownership import alternatives
HERE=Path(__file__).resolve().parent;HILL=HERE.parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from tools.rx_paired_opportunities import export_input,projected_candidates
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    started=time.monotonic();base=HILL.parent/'2026_09_30_ds11_single10';plan=read(base/'plan.json')
    sidepath=HILL/'source_consistency/source_groups.json';side=read(sidepath)
    idpath=HILL/'source_balance/catalogue_identities.json';identities=read(idpath)
    assert side['plan_sha256']==digest(base/'plan.json')
    sources={str(p):digest(p) for p in (base/'plan.json',sidepath,idpath,Path(__file__),HERE/'ownership.py',
             ROOT/'tools/rx_paired_opportunities.py',Path(inspect.getfile(ScannerTrackingInputStore)),Path(inspect.getfile(project_scanner_candidates)))}
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'));scans=[]
    try:
        for index in (0,16):
            entry=plan['inputs'][index]
            for a in entry['artifacts']:
                assert digest(a['path'])==a['sha256'].removeprefix('sha256:');sources[a['path']]=digest(a['path'])
            obs=read(next(a['path'] for a in entry['artifacts'] if a['kind']=='observations'))
            raw=store.load(entry['session_id'])
            assert raw.input_manifest_sha256==entry['manifest_sha256'] and raw.analysis_manifest_sha256==obs['analysis_manifest_sha256']
            assert raw.qualified and raw.timing.qualified
            projection=projected_candidates(raw)
            # No serialized cache exists here; this internal value explicitly
            # identifies a contract-content fingerprint, not a cache-file hash.
            fingerprint='public-input:'+raw.input_manifest_sha256+':'+raw.analysis_manifest_sha256
            opportunities,_=export_input(raw,split='ds11-pilot',cache_sha256=fingerprint,projected=projection)
            candidates={};window_by_id={o['source_window_id']:o for o in opportunities}
            for o in opportunities:
                assert o['opportunity_status'] in ('both_receivers_candidate_present','both_receivers_candidate_absent','one_receiver_candidate_present')
                for rx in ('rx0','rx1'):
                    for c in o['receivers'][rx]['candidates']:
                        cid=c['projected_candidate_id']
                        if cid is not None:
                            assert cid not in candidates
                            candidates[cid]=dict(window_id=o['source_window_id'],receiver=int(rx[-1]),rf_hz=o['receivers'][rx]['actual_rf_hz'])
            owners=defaultdict(list);tracks=[]
            for t in obs['tracks']:
                tid=t['track_id'];points=side['scans'][str(index)]['tracks'][tid]
                assert len(points)==len(t['times_s'])
                ids=[];wins=[]
                for j,p in enumerate(points):
                    cid=p['candidate_id'];c=candidates[cid];window=window_by_id[c['window_id']]
                    assert c['receiver']==t['receiver_id'] and c['rf_hz']==t['rf_hz']
                    assert window['source_window']['visit_index']==t['visits'][j] and p['training']==t['training_mask'][j]
                    ids.append(cid);wins.append(c['window_id']);owners[cid].append(tid)
                tracks.append(dict(track_id=tid,receiver=t['receiver_id'],rf_hz=t['rf_hz'],candidate_ids=ids,window_ids=wins,
                    training_mask=t['training_mask'],candidate_norad=identities['scans'][str(index)]['tracks'][tid]['candidate_norad']))
            lanes=[]
            for rf in sorted({t['rf_hz'] for t in tracks}):
                lane_tracks=[t for t in tracks if t['rf_hz']==rf];tids={t['track_id'] for t in lane_tracks}
                left=[t for t in lane_tracks if t['receiver']==0];right=[t for t in lane_tracks if t['receiver']==1];edges=[]
                for a in left:
                    for b in right:
                        common=sorted(set(a['candidate_norad'])&set(b['candidate_norad']))
                        aw={w for w,m in zip(a['window_ids'],a['training_mask']) if m};bw={w for w,m in zip(b['window_ids'],b['training_mask']) if m}
                        if common and aw&bw:edges.append(dict(left=a['track_id'],right=b['track_id'],candidate_norad=common,common_training_windows=len(aw&bw)))
                ambiguous={cid:ts for cid,ts in owners.items() if len(ts)>1 and set(ts)<=tids}
                states=alternatives(ambiguous)
                lanes.append(dict(rf_hz=rf,left=[t['track_id'] for t in left],right=[t['track_id'] for t in right],edges=edges,
                                  ambiguous_owners=ambiguous,ownership_alternatives=[dict(assignment=a,log_prior=w) for a,w in states]))
            path=HERE/f'input-{index:02d}.json'
            result=dict(index=index,session_id=entry['session_id'],input_manifest_sha256=raw.input_manifest_sha256,
                        analysis_manifest_sha256=raw.analysis_manifest_sha256,tracks=tracks,lanes=lanes,opportunities=opportunities,
                        unidentified_candidate_count=len(set(candidates)-set(owners)),sources=sources)
            with path.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
            scans.append(dict(index=index,path=str(path),sha256=digest(path),tracks=len(tracks),windows=len(opportunities),
                proposed_edges=sum(len(l['edges']) for l in lanes),ambiguous_detections=sum(len(l['ambiguous_owners']) for l in lanes),
                lane_ownership_states=[len(l['ownership_alternatives']) for l in lanes]))
    finally:store.close()
    outcome=dict(scans=scans,elapsed_s=time.monotonic()-started,sources=sources)
    with (HERE/'inputs.json').open('x') as f:json.dump(outcome,f,indent=2)
    print(json.dumps(dict(scans=scans,elapsed_s=outcome['elapsed_s']),indent=2))
if __name__=='__main__':main()
