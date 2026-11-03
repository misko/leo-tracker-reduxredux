"""Verify serialized older-bank coverage and independent spot propagation."""
import hashlib
import json
from pathlib import Path
import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records,parse_element_sets

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    inventory=json.loads((HILL/'ds11_revision_support/inventory.json').read_text())
    plan=json.loads((HILL.parent/'2026_09_30_ds11_single10/plan.json').read_text())
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));refs={str(r.path):r for r in archive.list_snapshots()};checks=[]
    for index in (0,16):
        metadata_path=HERE/f'{index:02d}.json';m=json.loads(metadata_path.read_text())
        for p,h in m['sources'].items():assert digest(p)==h
        assert digest(m['output_path'])==m['output_sha256']
        entry=plan['inputs'][index];obs=json.loads(Path(next(a['path'] for a in entry['artifacts'] if a['kind']=='observations')).read_text())
        original_path=next(a['path'] for a in entry['artifacts'] if a['path'].endswith('.npz'))
        tracks={r['track_id']:r for r in obs['tracks']}
        scan=next(s for s in inventory['scans'] if s['index']==index)
        records={r.satellite_number:r for r in parse_element_set_records(archive.read(refs[scan['older_snapshot_path']]))}
        maximum=0.;total=0
        with np.load(m['output_path'],allow_pickle=False) as new,np.load(original_path,allow_pickle=False) as old:
            np.testing.assert_array_equal(new['timing_grid_s'],old['timing_grid_s'])
            expected={'timing_grid_s'}
            for row in m['rows']:
                ti=row['index'];expected.update(f'{prefix}_{ti}' for prefix in ('position_km','velocity_km_s','candidate_ids'))
                np.testing.assert_array_equal(new[f'candidate_ids_{ti}'],old[f'candidate_ids_{ti}'])
                for prefix in ('position_km','velocity_km_s'):
                    array=new[f'{prefix}_{ti}'];assert array.shape==old[f'{prefix}_{ti}'].shape and np.isfinite(array).all()
                assert row['position_replay_error_km']<=1e-8 and row['velocity_replay_error_km_s']<=1e-10
                total+=row['candidates']
            assert set(new.files)==expected
            # First/last track, first/last candidate, first/last observation and
            # first/last timing node: new propagation independent of the saved loop.
            for row in (m['rows'][0],m['rows'][-1]):
                ti=row['index'];t=tracks[row['track_id']];obs_indices=[0,len(t['times_s'])-1];tau_indices=[0,len(new['timing_grid_s'])-1]
                for slot in (0,row['candidates']-1):
                    record=records[row['candidate_norad'][slot]]
                    cat=parse_element_sets(record.text)
                    p,v,ids=propagate_candidate_states(cat,[0],obs['start_utc_ns'],np.array(t['times_s'])[obs_indices],new['timing_grid_s'][tau_indices])
                    np.testing.assert_array_equal(ids,[0])
                    for actual,prefix in ((p,'position_km'),(v,'velocity_km_s')):
                        expected_array=new[f'{prefix}_{ti}'][slot][tau_indices][:,obs_indices]
                        error=float(np.max(abs(actual[0]-expected_array)));maximum=max(maximum,error)
                        assert error<1e-10
        checks.append(dict(index=index,tracks=len(m['rows']),candidate_track_occasions=total,maximum_spot_state_discrepancy=maximum,
                           metadata_sha256=digest(metadata_path),bank_sha256=m['output_sha256']))
    result=dict(verification_pass=True,scans=checks,full_original_replay_recorded=True,older_repropagation_scope='first/last tracks,candidates,observations,timing nodes',
                verifier_sha256=digest(Path(__file__)))
    with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
