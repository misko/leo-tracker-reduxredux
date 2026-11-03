"""Export qualified research evidence through the versioned T1-AT input contract.

Exercise the real adaptive stage against read-only capture/analysis manifests.
This bridge belongs to the reproducibility report, not the runtime package.
"""
import json
from pathlib import Path
import sys

from run import TopAbsoluteCalibration, digest

WORKTREE=Path('/srv/bulk/leo-dev/t1-at-integration-LxiJ1v')
sys.path.insert(0,str(WORKTREE/'src'))
from leo.cli.t1_at import run as pipeline
from leo.contracts.digests import canonical_digest
from leo.contracts.t1_at import T1AtCandidateV1,T1AtInputV1,T1AtModeV1

BASE=Path('/srv/bulk/leo/t1-at-v1-replication-20261004')
INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
HERE=Path(__file__).resolve().parent
OUT=BASE/'pipeline-integration'


def prepared_evidence(scan, *, include_modes=True):
    directory=INPUTS/scan/'seed-timing-v6'
    cal=TopAbsoluteCalibration(directory) # Verifies source inventories and convergence.
    association=BASE/('attempt2' if scan in ('N01','N02') else 'remaining')/scan
    pool=None
    if include_modes:
        pool=json.loads((association/'candidate-pool.json').read_text())
        for path,expected in pool['sources'].items():
            assert digest(Path(path).read_bytes())==expected,path
    observations=json.loads((directory/'observations.json').read_text())
    refined=json.loads((directory/'refinement/refined.json').read_text())
    refinements={r['row_index']:r for r in refined['records']}
    candidates=[]
    for row in observations['records']:
        result=refinements[row['row_index']]
        candidates.append(T1AtCandidateV1(candidate_id=row['row_index'],window_id=row['group_id'],
            receiver_id=row['receiver'],channel=row['channel'],receive_time_s=row['time_s'],
            refined_cfo_hz=result['output_hz'],refined_margin=result['refinement'].get('margin',result['original_margin']),
            refinement_state='refined' if result['refinement']['status']=='refined' else 'failed-original-retained'))
    def modes(arm):
        if pool is None: return ()
        return tuple(T1AtModeV1(catalog_number=m['catalog_number'],absolute_timing_s=m['offset_s'],
            candidate_ids=tuple(pool['original_rows'][i] for i in m['eligible_rows']),residual_hz=tuple(m['residual_hz']))
            for m in pool['arms'][arm])
    prepared=T1AtInputV1(session_id=cal.data.session_id,
        input_manifest_sha256=observations['signature']['manifest_sha256'],
        analysis_manifest_sha256=observations['analysis_manifest_sha256'],
        refinement_sha256=digest((directory/'refinement/refined.json').read_bytes()),
        calibration_sha256=canonical_digest({str(p):digest(p.read_bytes()) for p in sorted((directory/'calibration-v2').glob('fold-*.json'))}),
        orbit_bank_sha256=digest((directory/'orbit-bank/states.npz').read_bytes()),
        calibration_qualified=True,candidates=tuple(candidates),
        fitted_c_modes=modes('fitted-c'),zero_c_modes=modes('zero-c'))
    return cal, prepared, association


def exercise(scan):
    cal,prepared,association=prepared_evidence(scan)
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f'{scan}-input.json'
    payload=prepared.model_dump_json()
    if path.exists(): assert path.read_text()==payload
    else: path.write_text(payload)
    result=pipeline(capture_root=Path('/srv/bulk/leo'),analysis_root=Path('/srv/bulk/leo'),
        output_root=OUT,prepared_input=path,session_id=prepared.session_id,maximum_seconds=180)
    for arm,counts in result['coverage'].items():
        oracle=json.loads((association/f'{arm}.json').read_text())['final']
        assert counts['assigned']==oracle['assigned'],(scan,arm)
    result.update(scan=scan,input_contract=str(path),scope=__doc__)
    return result


if __name__=='__main__':
    results=[]
    for scan in ('N01','N02'):
        results.append(exercise(scan));print(json.dumps(results[-1]),flush=True)
        (HERE/'pipeline-integration-results.json').write_text(json.dumps(results,indent=2))
