"""Audit all window outcomes before reading reference coordinates for scoring."""
import argparse
import importlib.util
import json
from pathlib import Path
import time

import numpy as np
from run_common_clock import prepare_window
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def audit(directory):
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen=json.loads(freeze.read_text());verify_sources(frozen['source_sha256']);verify_sources(frozen['inputs'])
    rows=[];states={}
    for unit in frozen['units']:
        started=time.monotonic();path=directory/(unit['unit_id']+'.json')
        errors=[];receipt={};gradient_error=None;decrement=None;launch={}
        try:
            launch=json.loads(path.with_suffix('.launch.json').read_text())
            assert launch['returncode']==0 and launch['within_budget'] and not launch['timed_out']
            assert launch['freeze_sha256']==digest(freeze)
            assert digest(path)==launch['receipt_sha256']==path.with_suffix('.sha256').read_text().strip()
            receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256'])
            assert receipt['status']=='converged_local_mode',receipt.get('exception',receipt['status'])
            binding,scans,columns,precision,ports=prepare_window(unit['unit_id'])
            assert binding==receipt['binding']==unit
            assert receipt['inputs']=={k:v for scan,_,_ in scans for k,v in scan.inputs.items()}
            assert receipt['height']==scans[0][1].input_bindings
            assert receipt['columns']==[c.tolist() for c in columns]
            assert receipt['precision']==precision.tolist()
            assert receipt['observations']==[list(p.observation_ids) for p in ports]
            ids=[i for p in ports for i in p.observation_ids];assert len(ids)==len(set(ids))
            fit=receipt['best'];state=np.asarray(fit['mean']);assert state.shape==precision.shape
            assert np.all(np.isfinite(state)) and np.linalg.norm(state[:2])<=250
            assigned=[int(np.argmax(p.score_all(state))) for p in ports]
            assert assigned==fit['associations']
            active={0,1,*np.flatnonzero(state).tolist()};predictions=[]
            for p,i in zip(ports,assigned):
                if i<p.candidate_count:
                    pred=p.predict_selected(state,i);assert pred.eligible
                    predictions.append((p,pred))
                    active.update(np.flatnonzero(np.any(pred.jacobian!=0,axis=0)).tolist())
            active=np.array(sorted(active));metric=np.diag(precision[active]);gradient=(precision*state)[active]
            for p,pred in predictions:
                r=p.observation-pred.mean;solved=np.linalg.solve(pred.covariance,r)
                w=(4+len(r))/(4+float(r@solved));j=pred.jacobian[:,active]
                gradient-=w*j.T@solved;metric+=w*j.T@np.linalg.solve(pred.covariance,j)
            def objective(x):
                return float(.5*(precision*x)@x-sum(p.score_selected(x,i) for p,i in zip(ports,assigned)))
            value=objective(state)
            assert abs(value-fit['objectives'][-1])<1e-6
            assert np.all(np.diff(fit['objectives'])<=1e-6)
            finite=[]
            for index in active:
                shift=np.zeros(len(state));shift[index]=.0005
                finite.append((objective(state+shift)-objective(state-shift))/.001)
            finite=np.asarray(finite);gradient_error=float(np.max(abs(finite-gradient)))
            decrement=float(finite@np.linalg.solve(metric,finite))
            assert gradient_error<.005 and decrement<1e-5, f'gradient={gradient_error};decrement={decrement}'
            states[unit['unit_id']]=state[:2].tolist()
        except (AssertionError,ValueError,OSError,KeyError,np.linalg.LinAlgError) as error:
            errors.append(type(error).__name__+': '+str(error))
        row=dict(unit=unit['unit_id'],size=unit['size'],block_id=unit['block_id'],scans=unit['scans'],
            accepted=not errors,failures=errors,fit_status=receipt.get('status'),
            runtime_s=launch.get('elapsed_seconds'),cpu_s=receipt.get('cpu_seconds'),
            gradient_error=gradient_error,numeric_decrement_squared=decrement,
            receipt_sha256=launch.get('receipt_sha256'),audit_seconds=time.monotonic()-started)
        rows.append(row);print(json.dumps(row),flush=True)
    return rows,states,digest(freeze)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('block');args=parser.parse_args()
    directory=HERE/'common-clock-v1'/args.block
    rows,states,freeze_hash=audit(directory)
    # No reference is read until every numerical decision for this block is fixed.
    ref_path=HERE/'reference-admission-v1.json'
    assert digest(ref_path)==ref_path.with_suffix('.sha256').read_text().strip()
    references=json.loads(ref_path.read_text());verify_sources(references['source_sha256'])
    reference={r['unit']:r['reference_latlon'] for r in references['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        locations=[reference[u] for u in row['scans']]
        assert all(p==locations[0] for p in locations),'reference differs within window'
        row['error_m']=geo.distance_m(geo.latlon_from_enu(*states[row['unit']]),locations[0]) if row['accepted'] else None
    result=dict(rows=rows,freeze_sha256=freeze_hash,evaluator_sha256=digest(__file__),reference_sha256=digest(ref_path),
        qualification='Cold development pilot; all numerical outcomes audited before geography. Unsurveyed operator reference; no physical movement sensing. Quantiles require failure denominators; correlated windows are not independent trials.')
    output=directory/'evaluation.json'
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
