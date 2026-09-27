"""Metadata-only expanded phase selection using exact position-track membership."""
import json,pickle,hashlib,itertools
from pathlib import Path
from collections import defaultdict
from leo.application.scanner_trajectory import project_scanner_candidates
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SEED=2026092710
def wrap(x,p):return (x+p/2)%p-p/2
def epoch(c):return c.integer_epoch_sample+c.fractional_epoch_offset_samples
def main():
    source_path=ROOT/'2026_09_27_ds6_alltrack_phase/inputs.json';inputs=json.loads(source_path.read_text());sid=inputs['session_id']
    payload=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_27_roof_direction_subset/cache/'+sid+'.pickle').read_bytes();assert 'sha256:'+hashlib.sha256(payload).hexdigest()==inputs['tracking_cache_sha256'];raw=pickle.loads(payload)
    assert raw.input_manifest_sha256==inputs['input_manifest_sha256'] and raw.analysis_manifest_sha256==inputs['analysis_manifest_sha256']
    members=defaultdict(list);partition={}
    for track in inputs['tracks']:
        for cid,v,mask in zip(track['candidate_ids'],track['visits'],track['training_mask']):
            members[cid].append(track['track_id']);assert v not in partition or partition[v]==mask;partition[v]=mask
    bykey={(p.visit_index,p.receiver_id,p.probe_index,p.candidate_rank):p.candidate_id for p in project_scanner_candidates(raw)}
    probes=defaultdict(dict)
    for p in raw.probes:
        if p.probe_index==0:probes[p.visit_index][p.receiver_id]=p
    groups=defaultdict(dict);fs=raw.sample_rate_hz;combination_count=0
    for visit,rx in probes.items():
        if set(rx)!={0,1}:continue
        left=[c for c in rx[0].candidates if c.passed_fractional_margin_gate and len(members[bykey[visit,0,0,c.candidate_rank]])==1]
        right=[c for c in rx[1].candidates if c.passed_fractional_margin_gate]
        pairs=[(a,b) for a in left for b in right if abs(wrap(epoch(a)-epoch(b),fs/750))<=fs*3e-7]
        for first,second in itertools.combinations(pairs,2):
            a,b=first;c,d=second
            if a.candidate_rank==c.candidate_rank or b.candidate_rank==d.candidate_rank:continue
            if abs(a.fractional_tracking_cfo_hz-c.fractional_tracking_cfo_hz)<10000 or abs(wrap(epoch(a)-epoch(c),fs/750))<fs*5e-7:continue
            if abs((b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz)-(d.fractional_tracking_cfo_hz-c.fractional_tracking_cfo_hz))>2000:continue
            modes=[]
            for x,y in sorted([first,second],key=lambda p:p[0].fractional_tracking_cfo_hz):
                modes.append(dict(seeds=[dict(receiver_id=i,rank=z.candidate_rank,integer_epoch_sample=z.integer_epoch_sample,fractional_epoch_offset_samples=z.fractional_epoch_offset_samples,cfo_hz=z.fractional_tracking_cfo_hz,margin=z.fractional_margin) for i,z in enumerate([x,y])],candidate_ids=[bykey[visit,i,0,z.candidate_rank] for i,z in enumerate([x,y])],rx0_track_id=members[bykey[visit,0,0,x.candidate_rank]][0]))
            if modes[0]['rx0_track_id']==modes[1]['rx0_track_id']:continue
            key=json.dumps([rx[0].channel,rx[0].edge,*[m['rx0_track_id'] for m in modes]])
            item=dict(visit=visit,channel=rx[0].channel,edge=rx[0].edge,rf_center_hz=rx[0].actual_rf_hz,valid_start_counter=rx[0].valid_start_counter,modes=modes,group=key,partition='train' if partition[visit] else 'held',confidence=min(z.fractional_margin for z in [a,b,c,d]))
            combination_count+=1
            if visit not in groups[key] or item['confidence']>groups[key][visit]['confidence']:groups[key][visit]=item
    inventory=[];eligible=[]
    for key,d in groups.items():
        values=list(d.values());nt=sum(v['partition']=='train' for v in values);nh=len(values)-nt
        inventory.append(dict(group=key,visits=len(values),train=nt,held=nh))
        if nt>=2 and nh>=2:eligible.append((key,values))
    selected=[];selected_groups=[]
    for key,values in sorted(eligible,key=lambda kv:(-len(kv[1]),kv[0]))[:6]:
        chosen=[]
        for partition_name in ['train','held']:
            pool=[v for v in values if v['partition']==partition_name];pool.sort(key=lambda v:hashlib.sha256(f'{SEED}:{sid}:{key}:{v["visit"]}'.encode()).hexdigest());chosen.extend(pool[:4])
        selected.extend(chosen);selected_groups.append(dict(group=key,available=len(values),selected_visits=sorted(v['visit'] for v in chosen)))
    result=dict(session_id=sid,seed=SEED,source_inputs_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),input_manifest_sha256=inputs['input_manifest_sha256'],analysis_manifest_sha256=inputs['analysis_manifest_sha256'],rate_hz=fs,timing=raw.timing.model_dump(mode='json'),selection='Enumerate joint candidate pairs before strongest-pair pruning; require exact unique RX0 position-track joins; top six groups by metadata count; up to four hash-selected visits per existing train/held partition',starts_ms=[0,21,42,63,84,105],width_ms=7,eligible_candidate_combinations=combination_count,group_inventory=inventory,selected_groups=selected_groups,selected=sorted(selected,key=lambda v:(v['visit'],v['group'])))
    (HERE/'plan.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(groups=len(groups),eligible_groups=len(eligible),selected_groups=selected_groups,selected_group_visits=len(selected),distinct_visits=len({v['visit'] for v in selected})),indent=2))
if __name__=='__main__':main()
