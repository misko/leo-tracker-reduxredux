"""Test the runtime full-bank discovery stage against frozen scan oracles.

The research bridge exports calibrated orbit arrays, not satellite/timing modes.
The standard runtime performs all timing discovery and greedy/replacement work.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import numpy as np

from run import digest
from exercise_pipeline import prepared_evidence

WORKTREE=Path('/srv/bulk/leo-dev/t1-at-integration-LxiJ1v')
sys.path.insert(0,str(WORKTREE/'src'))
from leo.analysis.t1_at_prediction import T1AtPredictor
from leo.cli.t1_at import run as pipeline
from leo.contracts.t1_at_prediction import T1AtDiscoveryManifestV1,T1AtDiscoveryData
from leo.storage.t1_at import T1AtProductStore

BASE=Path('/srv/bulk/leo/t1-at-v1-replication-20261004')
INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
HERE=Path(__file__).resolve().parent


def exercise(scan):
    cal,evidence,association=prepared_evidence(scan,include_modes=False)
    from joint_inputs import _coordinates,_ecef
    correction=np.zeros((2,cal.group_count));observer=np.zeros((2,cal.group_count,3));up=np.zeros_like(observer)
    for destination,part,models in cal.parts:
        for a,arm in enumerate(('fitted-c','zero-c')):
            p,unused_reference,c=models[arm]
            lat,lon=_coordinates(p[:2]);latitude,longitude=np.deg2rad([lat,lon])
            observer[a,destination]=_ecef(lat,lon)
            up[a,destination]=[np.cos(latitude)*np.cos(longitude),np.cos(latitude)*np.sin(longitude),np.sin(latitude)]
            correction[a,destination]=c+p[2+2*part.receiver]+p[3+2*part.receiver]*(part.times-150)
    values=dict(candidate_ids=cal.data.original_rows,numbers=cal.data.numbers,nodes_s=cal.data.nodes,
        position_km=cal.data.position,velocity_km_s=cal.data.velocity,rf_hz=cal.data.rf,
        observer_km=observer[:,cal.inverse],up=up[:,cal.inverse],calibration_hz=correction[:,cal.inverse])
    output=BASE/'discovery-pipeline'/scan;output.mkdir(parents=True,exist_ok=True)
    bank_path=output/'prediction-bank.npz'
    if bank_path.exists():
        with np.load(bank_path,allow_pickle=False) as saved:
            assert set(saved.files)==set(values)
            for key,value in values.items(): np.testing.assert_array_equal(saved[key],value)
    else: np.savez_compressed(bank_path,**values)
    manifest=T1AtDiscoveryManifestV1(evidence=evidence,bank_sha256=digest(bank_path.read_bytes()))
    path=output/'input.json'
    if path.exists(): assert T1AtDiscoveryManifestV1.model_validate_json(path.read_bytes())==manifest
    else: path.write_text(manifest.model_dump_json())
    predictor=T1AtPredictor(T1AtDiscoveryData(manifest=manifest,**values))
    max_error=0.
    for arm in ('fitted-c','zero-c'):
        for offset in (-19.9,-.375,0.,2.125,19.9):
            ids=np.arange(0,len(cal.data.numbers),max(1,len(cal.data.numbers)//10))
            expected=cal.predict(arm,ids,offset);actual=predictor(arm,ids,offset)
            max_error=max(max_error,float(np.max(abs(expected[0]-actual[0]))))
            np.testing.assert_allclose(expected[0],actual[0],atol=1e-7,rtol=0)
            np.testing.assert_allclose(expected[2],actual[2],atol=1e-7,rtol=0)
            assert np.array_equal(expected[1],actual[1])
    result=pipeline(capture_root=Path('/srv/bulk/leo'),analysis_root=Path('/srv/bulk/leo'),
        output_root=output,discovery_input=path,session_id=evidence.session_id,maximum_seconds=600)
    product=T1AtProductStore(output).load(result['prepared_input_sha256'])
    for arm,counts in result['coverage'].items():
        oracle=json.loads((association/f'{arm}.json').read_text())['final']
        assert counts['assigned']==oracle['assigned'],(scan,arm,counts,oracle['assigned'])
        actual={a.candidate_id:a for a in product.arms[arm].final.assignments}
        expected={a['row_index']:a for a in oracle['assignments']}
        assert set(actual)==set(expected),(scan,arm,'membership differs')
        for row,a in actual.items():
            assert a.catalog_number==expected[row]['catalog_number'],(scan,arm,row,'owner differs')
            assert abs(a.residual_hz-expected[row]['residual_hz'])<1e-6,(scan,arm,row,'residual differs')
    result.update(scan=scan,discovery_input=str(path),prediction_max_error_hz=max_error,scope=__doc__,
                  exact_assignment_owners=True,residual_agreement_tolerance_hz=1e-6,
                  source_sha256=digest(Path(__file__).read_bytes()),
                  source_oracles={arm:digest((association/f'{arm}.json').read_bytes())
                                  for arm in ('fitted-c','zero-c')})
    (output/'runtime-verification.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scans',nargs='+',default=['N01','N02'],choices=[f'N{i:02}' for i in range(1,17)])
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(exercise,scan) for scan in args.scans]
        for future in as_completed(futures):
            results.append(future.result());print(json.dumps(results[-1]),flush=True)
            (HERE/'discovery-pipeline-results.json').write_text(json.dumps(sorted(results,key=lambda r:r['scan']),indent=2))
