"""Freeze a bounded DS5 metadata-selected phase experiment before raw IQ reads."""
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict
import hashlib,json
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig

HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/bulk/leo')
MANIFEST=Path('/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_26_ds5_since_local_midnight/manifest.json')
SIDS=['scan-fw-006056cf3db5b95a','scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']
SEED=20260927
ALIAS=1/4.4e-6

def epoch(c):return c.integer_epoch_sample+c.fractional_epoch_offset_samples
def cfo(c):return c.fractional_tracking_cfo_hz
def delta(a,b,period):return (a-b+period/2)%period-period/2

def main():
    rng=np.random.default_rng(SEED);ds=json.loads(MANIFEST.read_text())
    metadata={r['session_id']:r for r in ds['captures']}
    output=dict(seed=SEED,scan_selection='Three additional 10 MS/s scans: early 07:20, middle 09:50, late 12:00 UTC; metadata only, original 12:20 excluded.',
                ds5_manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                selection='top three recurring exact RX0 track-pair/channel/edge groups by visit count; randomly sample at most six visits per group; add up to six single-pair visits',
                split='random whole visits per pair group, half held; pilot train/held uses guarded whole symbol blocks; within-dwell window transfer is a separate conditional diagnostic',
                starts_ms=[0,21,42,63,84,105],width_ms=7,scans=[])
    store=ScannerTrackingInputStore(ROOT)
    try:
        for sid in SIDS:
            source=store.load(sid);assert source.sample_rate_hz==10_000_000
            candidates=project_scanner_candidates(source)
            graph=reconstruct_persistent_hop_trajectories(candidates,config=PersistentHopTrajectoryConfig())
            byid={c.candidate_id:c for c in candidates};membership=defaultdict(list)
            for tr in graph.tracklets:
                for pt in tr.points:
                    c=byid[pt.candidate_id];membership[c.visit_index,c.receiver_id,c.candidate_rank].append(tr.tracklet_id)
            probes=defaultdict(dict)
            for p in source.probes:
                if p.probe_index==0:probes[p.visit_index][p.receiver_id]=p
            eligible=[];groups=defaultdict(list)
            for visit,rs in probes.items():
                if set(rs)!={0,1}:continue
                left=[c for c in rs[0].candidates if c.passed_fractional_margin_gate]
                right=[c for c in rs[1].candidates if c.passed_fractional_margin_gate]
                # Shared epoch pairs estimate the current scan's hardware offset.
                # Requiring RX CFO equality modulo an alias would incorrectly
                # impose the earlier recording's LNB offset on other scans.
                pairs=[(a,b) for a in left for b in right if abs(delta(epoch(a),epoch(b),source.sample_rate_hz/750))<=3]
                pairs.sort(key=lambda p:(-min(c.fractional_margin for c in p),p[0].candidate_rank,p[1].candidate_rank))
                chosen=[]
                for a,b in pairs:
                    if chosen and abs((cfo(b)-cfo(a))-(cfo(chosen[0][1])-cfo(chosen[0][0])))>2000:continue
                    if any(abs(cfo(a)-cfo(x))<10000 or abs(delta(epoch(a),epoch(x),source.sample_rate_hz/750))<5 for x,y in chosen):continue
                    chosen.append((a,b))
                    if len(chosen)==2:break
                if not chosen:continue
                chosen.sort(key=lambda p:cfo(p[0]))
                modes=[]
                for a,b in chosen:
                    modes.append(dict(seeds=[dict(receiver_id=rx,integer_epoch_sample=c.integer_epoch_sample,fractional_epoch_offset_samples=c.fractional_epoch_offset_samples,tracking_absolute_baseband_cfo_hz=cfo(c),candidate_rank=c.candidate_rank) for rx,c in enumerate((a,b))],rx0_track_ids=membership[visit,0,a.candidate_rank],rx1_track_ids=membership[visit,1,b.candidate_rank]))
                item=dict(visit=visit,channel=rs[0].channel,edge=rs[0].edge,rf_center_hz=rs[0].actual_rf_hz,valid_start_counter=rs[0].valid_start_counter,modes=modes)
                eligible.append(item)
                if len(modes)==2 and all(m['rx0_track_ids'] for m in modes):
                    key=json.dumps([rs[0].channel,rs[0].edge,*[sorted(m['rx0_track_ids']) for m in modes]])
                    groups[key].append(item)
            selected=[];group_inventory=[]
            for key,visits in sorted(groups.items(),key=lambda kv:(-len(kv[1]),kv[0]))[:3]:
                if len(visits)<4:continue
                take=[visits[i] for i in sorted(rng.choice(len(visits),min(6,len(visits)),replace=False))]
                held=set(map(int,rng.choice([r['visit'] for r in take],len(take)//2,replace=False)))
                for r in take:r.update(group=key,partition='held' if r['visit'] in held else 'train')
                selected.extend(take);group_inventory.append(dict(key=key,eligible_visits=len(visits),selected_visits=[r['visit'] for r in take],held_visits=sorted(held)))
            selected_ids={r['visit'] for r in selected}
            other_pairs=[r for r in eligible if len(r['modes'])==2 and r['visit'] not in selected_ids]
            for i in sorted(rng.choice(len(other_pairs),min(6,len(other_pairs)),replace=False)):
                r=other_pairs[i];r.update(group='nonrecurrent-pair',partition='diagnostic');selected.append(r)
            singles=[r for r in eligible if len(r['modes'])==1]
            for i in sorted(rng.choice(len(singles),min(6,len(singles)),replace=False)):
                r=singles[i];r.update(group='single',partition='diagnostic');selected.append(r)
            scan=dict(session_id=sid,metadata=metadata[sid],input_manifest_sha256=source.input_manifest_sha256,analysis_manifest_sha256=source.analysis_manifest_sha256,track_count=len(graph.tracklets),all_visits=len(probes),eligible_joint_visits=len(eligible),eligible_two_mode_visits=sum(len(r['modes'])==2 for r in eligible),recurrent_pair_groups=group_inventory,selected=sorted(selected,key=lambda r:r['visit']))
            output['scans'].append(scan);print(sid,'joint',len(eligible),'two',scan['eligible_two_mode_visits'],'selected',len(selected),flush=True)
    finally:store.close()
    (HERE/'plan.json').write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
