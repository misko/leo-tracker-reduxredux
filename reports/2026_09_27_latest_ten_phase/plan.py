"""Freeze latest fully processed adaptive scans, then metadata-only dwell sampling."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import json,hashlib
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories,PersistentHopTrajectoryConfig

HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/bulk/leo')
SEED=2026092705
def wrap(x,period):return (x+period/2)%period-period/2
def epoch(c):return c.integer_epoch_sample+c.fractional_epoch_offset_samples

def main():
    HERE.mkdir(exist_ok=True);captures=AdaptiveHopIqStore(ROOT,read_only=True);analysis=AdaptiveHopAnalysisPresentationStore(ROOT);tracking=ScannerTrackingStore(ROOT);inputs=ScannerTrackingInputStore(ROOT)
    selection=HERE/'selection.json'
    if not selection.exists():
        checked=[];selected=[];started=datetime.now(timezone.utc).isoformat()
        for ns,sid in captures.history_index():
            cap=captures.inspect(sid);a=analysis.status_for_capture(cap,probe_stride_ms=120);t=tracking.status(sid)
            ok=cap.manifest.receipt.terminal.state=='completed' and cap.manifest.receipt.source_span_attested and a.state=='figures_ready' and t.state=='complete'
            row=dict(session_id=sid,capture_utc_ns=ns,capture_utc=datetime.fromtimestamp(ns/1e9,timezone.utc).isoformat(),capture_state=cap.manifest.receipt.terminal.state,glrt_state=a.state,tracking_state=t.state,selected=ok)
            checked.append(row)
            if ok:selected.append(sid)
            if len(selected)==10:break
        if len(selected)!=10:raise RuntimeError('Fewer than ten completed adaptive scans')
        selection.write_text(json.dumps(dict(started_utc=started,definition='Newest capture UTC among published adaptive captures: terminal completed, source span attested, GLRT figures_ready and tracking complete. Tracking completion may include deferred catalogue groups.',checked=checked,selected=selected),indent=2)+'\n')
    selected=json.loads(selection.read_text())['selected'];rng=np.random.default_rng(SEED)
    result=dict(seed=SEED,selection_sha256=hashlib.sha256(selection.read_bytes()).hexdigest(),starts_ms=[0,21,42,63,84,105],width_ms=7,selection='Up to two recurrent RX0 track-pair/channel/edge groups, six random visits each; six other two-mode visits; six single-mode visits. No raw phase used to select visits.',scans=[])
    for sid in selected:
        source=inputs.load(sid);cap=captures.inspect(sid);product=tracking.status(sid).product
        assert source.qualified and source.input_manifest_sha256==product.input_manifest_sha256 and source.analysis_manifest_sha256==product.analysis_manifest_sha256
        fs=source.sample_rate_hz;points=project_scanner_candidates(source);byid={p.candidate_id:p for p in points};members=defaultdict(list)
        graph=reconstruct_persistent_hop_trajectories(points,config=PersistentHopTrajectoryConfig())
        published={t.tracklet_id for t in product.tracklets}
        for tr in graph.tracklets:
            for pt in tr.points:
                p=byid[pt.candidate_id];members[p.visit_index,p.receiver_id,p.probe_index,p.candidate_rank].append(dict(track_id=tr.tracklet_id,published=tr.tracklet_id in published))
        probes=defaultdict(dict)
        for p in source.probes:
            if p.probe_index==0:probes[p.visit_index][p.receiver_id]=p
        eligible=[];groups=defaultdict(list)
        for visit,rs in probes.items():
            if set(rs)!={0,1}:continue
            left=[c for c in rs[0].candidates if c.passed_fractional_margin_gate];right=[c for c in rs[1].candidates if c.passed_fractional_margin_gate]
            pairs=[(a,b) for a in left for b in right if abs(wrap(epoch(a)-epoch(b),fs/750))<=fs*3e-7]
            pairs.sort(key=lambda p:(-min(c.fractional_margin for c in p),p[0].candidate_rank,p[1].candidate_rank));chosen=[]
            for a,b in pairs:
                if chosen and abs((b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz)-(chosen[0][1].fractional_tracking_cfo_hz-chosen[0][0].fractional_tracking_cfo_hz))>2000:continue
                if any(abs(a.fractional_tracking_cfo_hz-x.fractional_tracking_cfo_hz)<10000 or abs(wrap(epoch(a)-epoch(x),fs/750))<fs*5e-7 for x,y in chosen):continue
                chosen.append((a,b))
                if len(chosen)==2:break
            if not chosen:continue
            chosen.sort(key=lambda p:p[0].fractional_tracking_cfo_hz);modes=[]
            for a,b in chosen:
                modes.append(dict(seeds=[dict(receiver_id=rx,integer_epoch_sample=c.integer_epoch_sample,fractional_epoch_offset_samples=c.fractional_epoch_offset_samples,cfo_hz=c.fractional_tracking_cfo_hz,rank=c.candidate_rank,margin=c.fractional_margin) for rx,c in enumerate([a,b])],tracks=[members[visit,rx,0,c.candidate_rank] for rx,c in enumerate([a,b])]))
            v=cap.manifest.receipt.visits[visit]
            item=dict(visit=visit,channel=rs[0].channel,edge=rs[0].edge,rf_center_hz=rs[0].actual_rf_hz,valid_start_counter=rs[0].valid_start_counter,valid_samples=v.valid_sample_count,modes=modes)
            eligible.append(item)
            if len(modes)==2 and all(m['tracks'][0] for m in modes):
                key=json.dumps([item['channel'],item['edge'],*[sorted(x['track_id'] for x in m['tracks'][0]) for m in modes]])
                groups[key].append(item)
        chosen=[]
        for key,items in sorted(groups.items(),key=lambda kv:(-len(kv[1]),kv[0]))[:2]:
            if len(items)<4:continue
            take=[items[i] for i in sorted(rng.choice(len(items),min(6,len(items)),replace=False))];held=set(map(int,rng.choice([v['visit'] for v in take],len(take)//2,replace=False)))
            for v in take:v.update(group=key,partition='held' if v['visit'] in held else 'train')
            chosen.extend(take)
        seen={v['visit'] for v in chosen}
        for count,kind in [(2,'other-pair'),(1,'single')]:
            pool=[v for v in eligible if len(v['modes'])==count and v['visit'] not in seen]
            for i in sorted(rng.choice(len(pool),min(6,len(pool)),replace=False)):
                v=pool[i];v.update(group=kind,partition='diagnostic');chosen.append(v)
        row=dict(session_id=sid,rate_hz=fs,radio_id=source.radio_id,capture_utc_ns=source.timing.first_sample_estimate_utc_ns,timing=source.timing.model_dump(mode='json'),capture_digest=source.input_manifest_sha256,analysis_digest=source.analysis_manifest_sha256,tracking_configuration_digest=product.configuration_digest,all_visits=len(probes),joint_visits=len(eligible),two_mode_visits=sum(len(v['modes'])==2 for v in eligible),published_track_count=len(published),reconstructed_track_count=len(graph.tracklets),matched_published_track_count=sum(t.tracklet_id in published for t in graph.tracklets),deferred_catalogue_groups=product.deferred_group_count,selected=sorted(chosen,key=lambda v:v['visit']))
        result['scans'].append(row);(HERE/'plan.json').write_text(json.dumps(result,indent=2)+'\n');print(sid,fs,'joint',len(eligible),'two',row['two_mode_visits'],'selected',len(chosen),'trackmatches',row['matched_published_track_count'],flush=True)
    captures.close();inputs.close()

if __name__=='__main__':main()
