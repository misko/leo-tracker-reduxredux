"""Original baseline and frozen challengers on additional single recordings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import harness

HERE = Path(__file__).resolve().parent
ADDITIONAL = HERE/'additional'


def validate_export(index,capture,receipt,validated,exporter_sha256):
    assert receipt['index']==index and receipt['exit_code']==0
    assert receipt['source_sha256']==exporter_sha256
    assert validated['index']==index and validated['source_sha256']==exporter_sha256
    entry=validated['input']
    assert entry['session_id']==capture['session_id']
    assert entry['manifest_sha256']==capture['manifest_sha256']
    return entry


def assemble():
    frozen_path=HERE/'additional-plan.json'
    frozen = json.loads(frozen_path.read_text())
    exporter_path=HERE/'additional_export.py'
    exporter_digest=harness.digest(exporter_path)
    sources={str(frozen_path):harness.digest(frozen_path),
             str(exporter_path):exporter_digest,**frozen['source_sha256']}
    for name,expected in sources.items():
        assert harness.digest(name)==expected,name
    inputs = []
    for i, capture in enumerate(frozen['captures']):
        receipt_path=ADDITIONAL/f'export_{i:02d}.receipt.json'
        validated_path=ADDITIONAL/'exports'/f'{i:02d}'/'validated.json'
        receipt = json.loads(receipt_path.read_text())
        validated = json.loads(validated_path.read_text())
        entry=validate_export(i,capture,receipt,validated,exporter_digest)
        sources.update({str(p):harness.digest(p) for p in (receipt_path,validated_path)})
        for artifact in entry['artifacts']:
            assert 'sha256:'+harness.digest(artifact['path']) == artifact['sha256']
        inputs.append(entry)
    with (ADDITIONAL/'plan.json').open('x') as stream:
        json.dump(dict(config=frozen['config'],inputs=inputs,source_sha256=sources),stream,indent=2)
    (ADDITIONAL/'runs').mkdir(exist_ok=True)


def baseline_fit(index):
    import numpy as np
    from scipy.optimize import minimize
    sys.path.insert(0,str(harness.ROOT/'tools'))
    import ds7_fast_baseline_adapter as baseline
    baseline.baseline.profile=baseline.profile
    start=time.monotonic()
    plan=json.loads((ADDITIONAL/'plan.json').read_text())
    for name,expected in plan['source_sha256'].items():
        assert harness.digest(name)==expected,name
    entry=plan['inputs'][index]
    for artifact in entry['artifacts']:
        assert 'sha256:'+harness.digest(artifact['path'])==artifact['sha256']
    docs=baseline.load_documents(dict(config=plan['config'],inputs=[entry]))
    model=baseline.Stationary(docs[0],plan['config'])
    bounds=[(-12.,12.),(-12.,12.),(-5.,5.)]
    starts=[]
    for east in (-2.,0.,2.):
        def objective(x):
            score,g=model.evaluate(x,True)
            return -score,-g
        fit=minimize(objective,[east,0.,0.],jac=True,method='L-BFGS-B',bounds=bounds,
                     options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
        discrepancies=[]
        for axis,step in enumerate((1e-4,1e-4,1e-5)):
            delta=np.eye(3)[axis]*step
            num=(model.evaluate(fit.x+delta)[0]-model.evaluate(fit.x-delta)[0])/(2*step)
            discrepancies.append(abs(num+fit.jac[axis]))
        audit=float(max(discrepancies))
        qualified,boundary,gradient=harness.qualify(fit.success,fit.x,fit.jac,audit,bounds)
        starts.append(dict(x=fit.x.tolist(),score=float(-fit.fun),success=bool(fit.success),
                           message=str(fit.message),boundary=boundary,gradient=gradient,
                           audit=audit,qualified=qualified))
    valid=[s for s in starts if s['qualified']]
    selected=dict(max(valid,key=lambda s:s['score'])) if valid else None
    if selected:
        selected['estimate_deg']=list(model.coordinates(selected['x']))
    record=dict(index=index,session=entry['session_id'],method='iid',starts=starts,
                selected=selected,elapsed_s=time.monotonic()-start,
                sources={**plan['source_sha256'],**{str(p):harness.digest(p) for p in [Path(__file__),HERE/'harness.py',
                         ADDITIONAL/'plan.json',harness.ROOT/'tools/ds7_baseline_adapter.py',
                         harness.ROOT/'tools/ds7_fast_baseline_adapter.py']}})
    with (ADDITIONAL/'runs'/f'{index:02d}_iid.json').open('x') as stream:
        json.dump(record,stream,indent=2,allow_nan=False)


def batch_baseline():
    plan=json.loads((ADDITIONAL/'plan.json').read_text())
    for index in range(len(plan['inputs'])):
        receipt=ADDITIONAL/'runs'/f'{index:02d}_iid.receipt.json'
        log=ADDITIONAL/'runs'/f'{index:02d}_iid.log'
        if receipt.exists():
            continue
        if log.exists():
            raise RuntimeError('Unreceipted attempt requires process audit')
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                 'timeout','--kill-after=5s','90s','nice','-n','19',harness.PYTHON,
                 str(Path(__file__).resolve()),'baseline',str(index)]
        started=time.monotonic()
        with log.open('x') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        row=dict(index=index,exit_code=result.returncode,wall_s=time.monotonic()-started,command=command)
        with receipt.open('x') as stream:
            json.dump(row,stream,indent=2)
        print(json.dumps(row),flush=True)


def challenger_batch(family,variant):
    if family not in ('robust','block_robust','timing','source_balance'):
        raise ValueError('Other model families need an explicit additional-input adapter')
    plan=json.loads((ADDITIONAL/'plan.json').read_text())
    folder=HERE/family/'runs'/'additional'
    folder.mkdir(parents=True,exist_ok=True)
    for index in range(len(plan['inputs'])):
        base=folder/f'{variant}_{index:02d}'
        receipt=base.with_suffix('.receipt.json')
        if receipt.exists():
            continue
        if base.with_suffix('.log').exists() or base.with_suffix('.json').exists():
            raise RuntimeError('Unreceipted attempt requires process audit')
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                 'timeout','--kill-after=5s','90s','nice','-n','19',harness.PYTHON,
                 str(Path(__file__).resolve()),'challenger',family,variant,str(index)]
        started=time.monotonic()
        with base.with_suffix('.log').open('x') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        row=dict(family=family,variant=variant,index=index,exit_code=result.returncode,
                 wall_s=time.monotonic()-started,command=command)
        with receipt.open('x') as stream:
            json.dump(row,stream,indent=2)
        print(json.dumps(row),flush=True)


def challenger_fit(family,variant,index):
    harness.BASE=ADDITIONAL
    if family=='source_balance':
        if variant!='source_receiver_equal':
            raise ValueError('Only the frozen source winner is authorized here')
        import importlib.util
        from types import SimpleNamespace
        path=HERE/'source_balance'/'additional_adapter.py'
        spec=importlib.util.spec_from_file_location('ds11_additional_source_adapter',path)
        adapter=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        def build(documents,config,variant,index=None):
            model=adapter.build_additional_model(documents,config,index=index,
                plan_path=ADDITIONAL/'plan.json',runs_dir=ADDITIONAL/'runs',
                identity_sidecar_path=ADDITIONAL/'catalogue_identities.json',variant=variant)
            model.metadata['additional_runner_sha256']=harness.digest(__file__)
            model.metadata['additional_policy_sha256']=harness.digest(HERE/'additional-policy.md')
            return model
        harness.load_plugin=lambda name: SimpleNamespace(build_model=build)
    harness.fit_one(family,variant,index,'additional')


if __name__=='__main__':
    action=sys.argv[1]
    if action=='assemble':
        assemble()
    elif action=='baseline':
        baseline_fit(int(sys.argv[2]))
    elif action=='baseline_batch':
        batch_baseline()
    elif action=='challenger':
        challenger_fit(sys.argv[2],sys.argv[3],int(sys.argv[4]))
    elif action=='challenger_batch':
        challenger_batch(sys.argv[2],sys.argv[3])
    elif action=='summarize':
        harness.BASE=ADDITIONAL
        harness.summarize(sys.argv[2],'additional')
    else:
        raise ValueError(action)
