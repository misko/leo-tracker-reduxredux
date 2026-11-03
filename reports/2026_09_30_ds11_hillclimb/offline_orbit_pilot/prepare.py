"""Slot-preserving later-orbit patches; explicitly offline only."""
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
spec=importlib.util.spec_from_file_location('causal_patch_helpers',HILL/'causal_fresh/prepare.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
digest=helpers.digest


def main(index):
    started=time.monotonic();selection_path=HERE/'selection.json';selection=json.loads(selection_path.read_text())
    assert index in selection['selected']
    for p,h in selection['sources'].items():assert digest(Path(p))==h,p
    plan_path=HILL.parent/'2026_09_30_ds11_single10/plan.json';plan=json.loads(plan_path.read_text())
    inventory_path=HILL/'delayed_orbit_inventory/inventory.json';inventory=json.loads(inventory_path.read_text())
    identity_path=HILL/'source_balance/catalogue_identities.json';identities=json.loads(identity_path.read_text())
    for p,h in inventory['source_sha256'].items():assert digest(Path(p))==h,p
    entry=plan['inputs'][index];scan=next(s for s in inventory['scans'] if s['index']==index)
    paths=[Path(a['path']) for a in entry['artifacts']]
    for a,p in zip(entry['artifacts'],paths,strict=True):assert digest(p)==a['sha256'].removeprefix('sha256:')
    observation_path=Path(next(a['path'] for a in entry['artifacts'] if a['kind']=='observations'))
    manifest_path=Path(next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.json')))
    bank_path=Path(next(a['path'] for a in entry['artifacts'] if a['kind']=='candidates' and a['path'].endswith('.npz')))
    observations=json.loads(observation_path.read_text());manifest=json.loads(manifest_path.read_text())
    assert scan['session']==entry['session_id']==observations['session_id']==manifest['session_id']
    assert scan['start_utc_ns']==observations['start_utc_ns']
    side=identities['scans'][str(index)]
    for p,key in [(bank_path,'bank_sha256'),(manifest_path,'manifest_sha256'),(observation_path,'observation_sha256')]:assert digest(p)==side[key]
    reader=TleArchiveReader(Path('/var/lib/leo/tle'));providers={s['provider'] for s in manifest['provider_sources']}
    refs=[r for r in reader.list_snapshots() if r.provider in providers and r.collected_utc_ns<=scan['cutoff_utc_ns']]
    by_digest={}
    for ref in sorted(refs,key=lambda r:r.collected_utc_ns):by_digest[ref.digest]=ref
    cache={};used={}
    def record(row,kind):
        ref=by_digest[row[f'{kind}_snapshot']]
        if ref.digest not in cache:
            assert digest(ref.path)==ref.sha256
            parsed=parse_element_set_records(reader.read(ref));cache[ref.digest]={r.satellite_number:r for r in parsed}
            assert len(cache[ref.digest])==len(parsed)
        used[str(ref.path)]=dict(provider=ref.provider,collected_utc_ns=ref.collected_utc_ns,sha256=ref.sha256,request_offset_from_capture_s=(ref.collected_utc_ns-scan['start_utc_ns'])/1e9)
        r=cache[ref.digest][row['norad']];assert helpers.element_digest(r)==row[f'{kind}_element_sha256']
        return r
    changed={r['norad']:r for r in scan['candidates'] if r['changed']}
    observation_tracks={r['track_id']:r for r in observations['tracks']}
    arrays={};rows=[];pe=ve=0.
    with np.load(bank_path,allow_pickle=False) as bank:
        timing=bank['timing_grid_s'];np.testing.assert_array_equal(timing,plan['config']['timing_grid_s'])
        for item in manifest['tracks']:
            ti=item['index'];tid=item['track_id'];mapping=side['tracks'][tid]
            ids=bank[f'candidate_ids_{ti}'];np.testing.assert_array_equal(ids,mapping['candidate_ids'])
            norads=np.array(mapping['candidate_norad']);slots=helpers.changed_slots(ids,norads,changed)
            if not len(slots):continue
            originals=[record(changed[int(n)],'original') for n in norads[slots]]
            replacements=[record(changed[int(n)],'delayed') for n in norads[slots]]
            times=np.array(observation_tracks[tid]['times_s'])
            old=helpers.catalogue(originals);new=helpers.catalogue(replacements)
            assert list(old.satellite_numbers)==list(new.satellite_numbers)==norads[slots].tolist()
            op,ov,valid=propagate_candidate_states(old,range(len(slots)),observations['start_utc_ns'],times,timing)
            np.testing.assert_array_equal(valid,np.arange(len(slots)))
            ep,ev=helpers.replay_error(op,ov,bank[f'position_km_{ti}'][slots],bank[f'velocity_km_s_{ti}'][slots]);pe=max(pe,ep);ve=max(ve,ev)
            p,v,valid=propagate_candidate_states(new,range(len(slots)),observations['start_utc_ns'],times,timing)
            np.testing.assert_array_equal(valid,np.arange(len(slots)))
            sk,pk,vk=f'slots_{ti}',f'position_km_{ti}',f'velocity_km_s_{ti}'
            arrays.update({sk:slots,pk:p,vk:v})
            rows.append(dict(index=ti,track_id=tid,slots_key=sk,position_key=pk,velocity_key=vk,norads=norads[slots].tolist(),candidate_ids=ids[slots].tolist()))
    array_path=HERE/f'patch-{index:02d}.npz'
    with array_path.open('xb') as f:np.savez(f,**arrays)
    paths += [Path(__file__),HERE/'PROTOCOL.md',selection_path,plan_path,inventory_path,identity_path,HILL/'causal_fresh/prepare.py',array_path,Path(inspect.getfile(propagate_candidate_states)),Path(inspect.getfile(helpers.parse_element_sets))]+[Path(p) for p in used]
    result=dict(schema='ds11-offline-orbit-patch/v1',index=index,session_id=entry['session_id'],offline_only=True,timing_grid_s=timing.tolist(),array_path=str(array_path),tracks=rows,archive_occurrences=used,replay=dict(position_max_abs_km=pe,velocity_max_abs_km_s=ve),inventory_fallbacks=sum(r['fallback'] for r in scan['candidates']),changed_candidates=len(changed),newer_epoch_candidates=sum(r['delayed_epoch_ns']>r['original_epoch_ns'] for r in scan['candidates']),sources={str(p):digest(p) for p in paths},elapsed_s=time.monotonic()-started)
    with (HERE/f'patch-{index:02d}.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(index=index,tracks=len(rows),replay=result['replay'],changed_candidates=len(changed),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main(int(sys.argv[1]))
