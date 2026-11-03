"""Slot-preserving older orbit states, with exact original-bank replay."""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate_slots(actual,expected):
    actual=np.asarray(actual);expected=np.asarray(expected)
    assert actual.shape==expected.shape and np.array_equal(actual,expected)
    assert len(set(actual.tolist()))==len(actual)
def main(index):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records,parse_element_sets
    started=time.monotonic();inventory_path=HILL/'ds11_revision_support/inventory.json';inventory=json.loads(inventory_path.read_text())
    sources=dict(inventory['sources'])
    for name,h in sources.items():assert digest(name)==h
    scan=next(s for s in inventory['scans'] if s['index']==index)
    base=HILL.parent/'2026_09_30_ds11_single10';plan_path=base/'plan.json';plan=json.loads(plan_path.read_text());entry=plan['inputs'][index]
    artifacts={}
    for a in entry['artifacts']:
        assert digest(a['path'])==a['sha256'].removeprefix('sha256:');sources[a['path']]=digest(a['path'])
        artifacts['observations' if a['kind']=='observations' else Path(a['path']).suffix]=Path(a['path'])
    obs=json.loads(artifacts['observations'].read_text());manifest=json.loads(artifacts['.json'].read_text())
    assert obs['session_id']==manifest['session_id']==scan['session_id']==entry['session_id']
    assert obs['start_utc_ns']==scan['start_utc_ns']
    sidecar_path=HILL/'source_balance/catalogue_identities.json';identity=json.loads(sidecar_path.read_text())
    assert identity['plan_sha256']==digest(plan_path)
    side=identity['scans'][str(index)];assert side['bank_sha256']==digest(artifacts['.npz'])
    reader=TleArchiveReader(Path('/var/lib/leo/tle'));refs={str(r.path):r for r in reader.list_snapshots()};cache={}
    def record(path,number,expected):
        ref=refs[path];metadata=inventory['snapshots'][path]
        assert ref.sha256==metadata['sha256'] and ref.collected_utc_ns==metadata['collected_utc_ns'] and ref.provider==metadata['provider']
        assert ref.collected_utc_ns<scan['cutoff_utc_ns']
        if path not in cache:
            parsed=parse_element_set_records(reader.read(ref));cache[path]={r.satellite_number:r for r in parsed}
            assert len(cache[path])==len(parsed)
            sources[path]=ref.sha256
        r=cache[path][number]
        assert hashlib.sha256((r.first_line+'\n'+r.second_line+'\n').encode()).hexdigest()==expected
        return r
    def catalogue(records):
        text=''.join(f'0 {r.name}\n{r.first_line}\n{r.second_line}\n' for r in records)
        return parse_element_sets(text)
    by_norad={r['norad']:r for r in scan['candidates']};tracks={t['track_id']:t for t in obs['tracks']}
    rows=[];arrays={};maxp=0.;maxv=0.
    with np.load(artifacts['.npz'],allow_pickle=False) as bank:
        timing=bank['timing_grid_s'];np.testing.assert_array_equal(timing,np.array(plan['config']['timing_grid_s']))
        arrays['timing_grid_s']=timing.copy()
        for item in manifest['tracks']:
            ti=item['index'];tid=item['track_id'];mapping=side['tracks'][tid]
            ids=bank[f'candidate_ids_{ti}'];validate_slots(ids,mapping['candidate_ids'])
            norads=mapping['candidate_norad'];assert len(norads)==len(ids)
            states={}
            for prefix in ('original','older'):
                records=[record(by_norad[n][prefix+'_snapshot_path'],n,by_norad[n][prefix+'_element_sha256']) for n in norads]
                cat=catalogue(records);assert list(cat.satellite_numbers)==norads
                p,v,valid=propagate_candidate_states(cat,range(len(ids)),obs['start_utc_ns'],np.array(tracks[tid]['times_s']),timing)
                validate_slots(valid,np.arange(len(ids)))
                assert p.shape==v.shape==(len(ids),len(timing),len(tracks[tid]['times_s']),3)
                assert np.isfinite(p).all() and np.isfinite(v).all()
                states[prefix]=(p,v)
            dp=float(np.max(abs(states['original'][0]-bank[f'position_km_{ti}'])));dv=float(np.max(abs(states['original'][1]-bank[f'velocity_km_s_{ti}'])))
            assert dp<=1e-8 and dv<=1e-10
            maxp=max(maxp,dp);maxv=max(maxv,dv)
            arrays[f'position_km_{ti}']=states['older'][0];arrays[f'velocity_km_s_{ti}']=states['older'][1]
            arrays[f'candidate_ids_{ti}']=ids.copy()
            rows.append(dict(index=ti,track_id=tid,candidate_norad=norads,candidates=len(ids),observations=len(tracks[tid]['times_s']),position_replay_error_km=dp,velocity_replay_error_km_s=dv))
    output_path=HERE/f'{index:02d}.npz'
    with output_path.open('xb') as f:np.savez_compressed(f,**arrays)
    for p in (inventory_path,plan_path,sidecar_path,Path(__file__),HERE/'PROTOCOL.md',HERE/'test_run.py',Path(inspect.getfile(propagate_candidate_states)),Path(inspect.getfile(parse_element_sets))):sources[str(p)]=digest(p)
    result=dict(index=index,session_id=scan['session_id'],rows=rows,sources=sources,output_path=str(output_path),output_sha256=digest(output_path),
                maximum_position_replay_error_km=maxp,maximum_velocity_replay_error_km_s=maxv,
                position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/f'{index:02d}.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','sources')},indent=2))
if __name__=='__main__':main(int(sys.argv[1]))
