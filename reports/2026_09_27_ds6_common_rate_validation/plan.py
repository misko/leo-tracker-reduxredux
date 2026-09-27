"""Freeze four new phase scans before reading IQ, then prepare exact track joins."""
import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SEED=2026092711


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ranking(value):
    return hashlib.sha256(f'{SEED}:{value}'.encode()).hexdigest()


def freeze():
    path=HERE/'protocol.json'
    if path.exists():
        raise FileExistsError('Protocol already frozen')
    inventory_path=ROOT/'2026_09_27_ds6_roof/approved-inventory.json'
    old_path=ROOT/'2026_09_27_latest_ten_phase/plan.json'
    old={r['session_id'] for r in json.loads(old_path.read_text())['scans']}
    inventory=json.loads(inventory_path.read_text())['captures']
    selected=[]
    for rate in [2.5,5.,7.5,10.]:
        eligible=sorted([r for r in inventory if r['session_id'] not in old and
                         r['sample_rate_msps']==rate and r['analysis']=='figures_ready' and
                         r['tracking']=='complete'],key=lambda r:ranking(r['session_id']))
        assert eligible
        selected.append(eligible[0])
    source_paths=[ROOT/'2026_09_27_ds6_position_linked_phase/common_rate.py',
                  ROOT/'2026_09_27_latest_ten_phase/phase.py',
                  ROOT/'2026_09_27_ds6_dwell_phase/experiment.py']
    result=dict(seed=SEED,inventory_sha256=digest(inventory_path),prior_phase_plan_sha256=digest(old_path),
                selection='One hash-selected scan per rate from completed DS6 scans outside the prior ten-scan phase replay; no replacements',
                source_sha256={str(p.relative_to(ROOT)):digest(p) for p in source_paths},
                selected=selected,starts_ms=[0,21,42,63,84,105],width_ms=7,
                visit_selection='Up to two disjoint exact positioning-track pairs ranked by eligible metadata visits, two hash-selected whole visits per existing hash partition',
                primary='For each scan, mean squared held pilot phase prediction error averaged first within window then equally across qualified windows. Compare frozen shared rate against unit-phasor independent rates.',
                decision='Promote only if at least three of four scans are evaluable and improve, and the equal-scan mean squared error improves. Otherwise retain as experimental.',
                diagnostics=['Within-dwell circular coherence; single-window dwell excluded from median',
                             'Train/evaluation DD disagreement','RX1 roll173us control on first window of every selected dwell'],
                limitations='Four scans from same capture night; validation of extraction only, no satellite IDs or position accuracy. Prior analyses other than this phase replay may have used these recordings.')
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(selected,indent=2))


def partition(sid,visit):
    return int(ranking(f'visit:{sid}:{visit}')[:8],16)%10<6


def prepare():
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    import numpy as np
    protocol=json.loads((HERE/'protocol.json').read_text())
    for name,sha in protocol['source_sha256'].items():assert digest(ROOT/name)==sha
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    captures=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    try:
        for record in protocol['selected']:
            sid=record['session_id'];path=HERE/(sid+'-plan.json')
            if path.exists():
                assert json.loads(path.read_text())['protocol_sha256']==digest(HERE/'protocol.json')
                print('Prepared already',sid,flush=True);continue
            print('Loading metadata',sid,flush=True)
            raw=store.load(sid);cap=captures.inspect(sid)
            assert raw.qualified and raw.input_manifest_sha256==cap.manifest_sha256==record['manifest_sha256']
            class Inputs:
                def load(self,session):
                    assert session==sid
                    return raw
            prepared=prepare_adaptive_tle_position_inputs(sid,inputs=Inputs(),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
            points=project_scanner_candidates(raw);byid={p.candidate_id:p for p in points}
            bykey={(p.visit_index,p.receiver_id,p.probe_index,p.candidate_rank):p.candidate_id for p in points}
            graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6))
            position={t.track_id:t for t in prepared.tracks};members=defaultdict(list);tracks=[]
            for track in graph.tracklets:
                if track.tracklet_id not in position:continue
                pts=[byid[p.candidate_id] for p in track.points];num=position[track.tracklet_id]
                np.testing.assert_allclose([(p.support_center_utc_ns-prepared.start_utc_ns)/1e9 for p in pts],num.times_s,rtol=0,atol=1e-9)
                for p in pts:members[p.candidate_id].append(track.tracklet_id)
                tracks.append(dict(track_id=track.tracklet_id,times_s=num.times_s.tolist(),measured_hz=num.measured_hz.tolist(),
                    training_mask=[partition(sid,p.visit_index) for p in pts],receiver_id=pts[0].receiver_id,
                    channel=pts[0].channel,rf_hz=pts[0].actual_rf_hz,visits=[p.visit_index for p in pts],candidate_ids=[p.candidate_id for p in pts]))
            assert {t['track_id'] for t in tracks}==set(position)
            fs=raw.sample_rate_hz;probes=defaultdict(dict);groups=defaultdict(dict)
            def epoch(c):return c.integer_epoch_sample+c.fractional_epoch_offset_samples
            def wrap(x):return (x+fs/1500)%(fs/750)-fs/1500
            for p in raw.probes:
                if p.probe_index==0:probes[p.visit_index][p.receiver_id]=p
            for visit,rx in probes.items():
                if set(rx)!={0,1}:continue
                assert (rx[0].channel,rx[0].edge,rx[0].valid_start_counter)==(rx[1].channel,rx[1].edge,rx[1].valid_start_counter)
                left=[c for c in rx[0].candidates if c.passed_fractional_margin_gate and len(members[bykey[visit,0,0,c.candidate_rank]])==1]
                right=[c for c in rx[1].candidates if c.passed_fractional_margin_gate]
                pairs=[(a,b) for a in left for b in right if abs(wrap(epoch(a)-epoch(b)))<=fs*3e-7]
                for first,second in itertools.combinations(pairs,2):
                    a,b=first;c,d=second
                    if a.candidate_rank==c.candidate_rank or b.candidate_rank==d.candidate_rank:continue
                    if abs(a.fractional_tracking_cfo_hz-c.fractional_tracking_cfo_hz)<10000 or abs(wrap(epoch(a)-epoch(c)))<fs*5e-7:continue
                    if abs((b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz)-(d.fractional_tracking_cfo_hz-c.fractional_tracking_cfo_hz))>2000:continue
                    modes=[]
                    for x,y in sorted([first,second],key=lambda p:p[0].fractional_tracking_cfo_hz):
                        modes.append(dict(seeds=[dict(receiver_id=i,rank=z.candidate_rank,integer_epoch_sample=z.integer_epoch_sample,
                            fractional_epoch_offset_samples=z.fractional_epoch_offset_samples,cfo_hz=z.fractional_tracking_cfo_hz,margin=z.fractional_margin)
                            for i,z in enumerate([x,y])],candidate_ids=[bykey[visit,i,0,z.candidate_rank] for i,z in enumerate([x,y])],rx0_track_id=members[bykey[visit,0,0,x.candidate_rank]][0]))
                    if modes[0]['rx0_track_id']==modes[1]['rx0_track_id']:continue
                    key=json.dumps([rx[0].channel,rx[0].edge,*[m['rx0_track_id'] for m in modes]])
                    item=dict(visit=visit,channel=rx[0].channel,edge=rx[0].edge,rf_center_hz=rx[0].actual_rf_hz,
                        valid_start_counter=rx[0].valid_start_counter,valid_samples=cap.manifest.receipt.visits[visit].valid_sample_count,
                        modes=modes,group=key,partition='train' if partition(sid,visit) else 'held',confidence=min(z.fractional_margin for z in [a,b,c,d]))
                    if visit not in groups[key] or item['confidence']>groups[key][visit]['confidence']:groups[key][visit]=item
            inventory=[];eligible=[]
            for key,visits in groups.items():
                nt=sum(v['partition']=='train' for v in visits.values());nh=len(visits)-nt
                inventory.append(dict(group=key,visits=len(visits),train=nt,held=nh))
                if nt>=2 and nh>=2:eligible.append((key,list(visits.values())))
            chosen=[];chosen_groups=[];used=set()
            for key,values in sorted(eligible,key=lambda kv:(-len(kv[1]),kv[0])):
                tids={m['rx0_track_id'] for m in values[0]['modes']}
                if tids&used:continue
                used|=tids;take=[]
                for part in ['train','held']:
                    pool=sorted([v for v in values if v['partition']==part],key=lambda v:ranking(f'{sid}:{key}:{v["visit"]}'))
                    take+=pool[:2]
                chosen+=take;chosen_groups.append(dict(group=key,available=len(values),selected_visits=sorted(v['visit'] for v in take)))
                if len(chosen_groups)==2:break
            result=dict(session_id=sid,protocol_sha256=digest(HERE/'protocol.json'),input_manifest_sha256=raw.input_manifest_sha256,
                analysis_manifest_sha256=raw.analysis_manifest_sha256,rate_hz=fs,timing=raw.timing.model_dump(mode='json'),
                start_utc_ns=prepared.start_utc_ns,snapshot_digest=prepared.snapshot_digest,evidence_sha256=prepared.evidence_sha256,
                tracks=tracks,group_inventory=inventory,selected_groups=chosen_groups,selected=sorted(chosen,key=lambda v:(v['visit'],v['group'])))
            path.write_text(json.dumps(result,indent=2)+'\n')
            print(sid,'tracks',len(tracks),'groups',len(chosen_groups),'visits',len(chosen),flush=True)
    finally:
        store.close();captures.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','prepare']);args=parser.parse_args()
    freeze() if args.action=='freeze' else prepare()
