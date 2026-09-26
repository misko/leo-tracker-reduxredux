"""Phase-blind longer-overlap selection from strong RX1 acquisition tracks."""
from pathlib import Path
from collections import defaultdict
import itertools,json
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig

HERE=Path(__file__).resolve().parent
OUT=HERE/'long-overlap'
RATE=10_000_000

def epoch(c):return c.integer_epoch_sample+c.fractional_epoch_offset_samples
def distance(a,b):return abs((a-b+RATE/1500)%(RATE/750)-RATE/1500)

def main():
    original=json.loads((HERE/'plan.json').read_text());rng=np.random.default_rng(20260928)
    output=dict(seed=20260928,selection='Per scan: longest co-observed distinct-epoch RX1 track pair in one RF lane, at least eight visits and 20 seconds; sample six visits in each of three chronological metadata strata',starts_ms=[0,21,42,63,84,105],width_ms=7,scans=[])
    OUT.mkdir(exist_ok=True)
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for scan in original['scans']:
            sid=scan['session_id'];source=store.load(sid);start=source.timing.session_start_device_sample_counter
            probes={(p.visit_index,p.receiver_id):p for p in source.probes if p.probe_index==0}
            bykey={(p.visit_index,p.receiver_id,c.candidate_rank):c for p in source.probes if p.probe_index==0 for c in p.candidates}
            points=project_scanner_candidates(source);byid={p.candidate_id:p for p in points}
            graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig(minimum_span_s=3,minimum_support=6))
            offsets=[]
            for (v,rx),p in probes.items():
                if rx!=0 or (v,1) not in probes:continue
                for a in p.candidates:
                    if not a.passed_fractional_margin_gate:continue
                    for b in probes[v,1].candidates:
                        if b.passed_fractional_margin_gate and distance(epoch(a),epoch(b))<=3:
                            offsets.append(((p.valid_start_counter-start)/RATE,b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz))
            a=np.asarray(offsets);binid=np.rint(a[:,1]/1000).astype(int);bins,counts=np.unique(binid,return_counts=True);peak=bins[np.argmax(counts)]*1000
            keep=abs(a[:,1]-peak)<2000
            slope,intercept=np.polyfit(a[keep,0],a[keep,1],1)
            curves=[]
            for track in graph.tracklets:
                if track.lane_key[2]!=1:continue
                visits={}
                for point in track.points:
                    p=byid[point.candidate_id];c=bykey[p.visit_index,p.receiver_id,p.candidate_rank]
                    if c.passed_fractional_margin_gate and (p.visit_index not in visits or c.fractional_margin>visits[p.visit_index].fractional_margin):visits[p.visit_index]=c
                curves.append((track,visits))
            possibilities=[]
            for (left,lv),(right,rv) in itertools.combinations(curves,2):
                if left.lane_key!=right.lane_key:continue
                common=[v for v in sorted(lv.keys()&rv.keys()) if distance(epoch(lv[v]),epoch(rv[v]))>5 and abs(lv[v].fractional_tracking_cfo_hz-rv[v].fractional_tracking_cfo_hz)>10000]
                if len(common)<8:continue
                times=np.array([(probes[v,1].valid_start_counter-start)/RATE for v in common]);span=float(np.ptp(times))
                if span>=20:possibilities.append((span,len(common),left.tracklet_id,right.tracklet_id,common,lv,rv))
            if not possibilities:
                output['scans'].append(dict(session_id=sid,metadata=scan['metadata'],selected=[],status='no qualifying RX1 pair',eligible_pair_count=0));continue
            span,count,leftid,rightid,common,lv,rv=max(possibilities,key=lambda p:(p[0],p[1],p[2],p[3]))
            selected=[]
            for stratum in np.array_split(np.array(common),3):
                selected.extend(sorted(map(int,rng.choice(stratum,min(6,len(stratum)),replace=False))))
            visits=[]
            for v in sorted(selected):
                p=probes[v,1];time=(p.valid_start_counter-start)/RATE;authority=float(intercept+slope*time);modes=[]
                for tid,c in ((leftid,lv[v]),(rightid,rv[v])):
                    f0=c.fractional_tracking_cfo_hz-authority
                    seeds=[dict(receiver_id=rx,integer_epoch_sample=c.integer_epoch_sample,fractional_epoch_offset_samples=c.fractional_epoch_offset_samples,tracking_absolute_baseband_cfo_hz=float(f0+rx*authority),candidate_rank=c.candidate_rank if rx==1 else -1) for rx in (0,1)]
                    modes.append(dict(seeds=seeds,rx0_track_ids=[],rx1_track_ids=[tid],authority='RX1 acquired; RX0 counterpart guided by scan-level shared epoch frequency offsets'))
                visits.append(dict(visit=v,channel=p.channel,edge=p.edge,rf_center_hz=p.actual_rf_hz,valid_start_counter=p.valid_start_counter,modes=modes,group=json.dumps([p.channel,p.edge,leftid,rightid]),partition='diagnostic'))
            output['scans'].append(dict(session_id=sid,metadata=scan['metadata'],status='selected',eligible_pair_count=len(possibilities),common_visits=count,common_span_s=span,track_ids=[leftid,rightid],receiver_offset_intercept_hz=float(intercept),receiver_offset_slope_hz_s=float(slope),offset_pair_count=int(keep.sum()),offset_residual_rms_hz=float(np.sqrt(np.mean((a[keep,1]-intercept-slope*a[keep,0])**2))),selected=visits))
            print(sid,'span',span,'common',count,'selected',len(visits),'offset residual',output['scans'][-1]['offset_residual_rms_hz'],flush=True)
    finally:store.close()
    (OUT/'plan.json').write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
