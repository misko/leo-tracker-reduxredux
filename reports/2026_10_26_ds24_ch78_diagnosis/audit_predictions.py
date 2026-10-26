"""Replay fixed-position scores to recover missing convergence diagnostics.

Does not optimize position, change a model, or overwrite original evidence.
"""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import time
import numpy as np
from common import *

residual=module('frozen_residual_driver',ROOT/'residual/run.py')
OUT=ROOT/'prediction_audit'


def one(path):
    began=time.monotonic();cap(240);saved=load(path);case=saved['case'];name=saved['mask']
    result=dict(case=case,mask=name,original_result_sha256=sha(path),GPS_used=False,checks=[])
    try:
        verify(load(ROOT/'residual/protocol.json')['sources'])
        d=context(case);j=saved['selected']['family'];rx=None if name=='whole' else int(name[-1])
        train,held,targets=residual.split(d,j,rx);unseen=[j] if rx is None else []
        original=h.fixed_position_posterior
        for arm,b in saved['arms'].items():
            for model,scores in b['crossover'].items():
                for endpoint,old in scores.items():
                    x=b['fits'][endpoint]['endpoint_east_north_km']
                    p,c,changes=original(train,unseen,arm,model,x)
                    precision=float(c['final_log_precision_change'])
                    maxphase=float(np.max(abs(p.state(x)['phases'][p.labels])))
                    h.fixed_position_posterior=lambda *_:(p,c,changes)
                    dest=OUT/'arrays'/f'{case}_{name}_{arm}_{model}_at_{endpoint}.npz'
                    new=residual.predict(d,train,held,targets,unseen,arm,model,x,dest)
                    h.fixed_position_posterior=original
                    previous=np.load(old['arrays']);current=np.load(dest)
                    assert set(previous.files)==set(current.files)
                    for k in previous.files:np.testing.assert_array_equal(previous[k],current[k])
                    assert old['scores']==new['scores']
                    result['checks'].append(dict(arm=arm,model=model,endpoint=endpoint,
                        all_score_arrays_and_scores_exact=True,final_log_precision_change=precision,
                        final_phase_change_s=changes[-1],maximum_unclipped_phase_s=maxphase,
                        checks_pass=bool(precision<=1.0001e-5 and changes[-1]<=.01 and maxphase<=15.000001),
                        replay_arrays_sha256=sha(dest)))
        result['status']='complete'
    except Exception as e:
        import traceback
        result.update(status='failed',error=repr(e),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result['seconds']=time.monotonic()-began;write(OUT/f'{case}_{name}.json',result)
    print(case,name,result['status'],len(result['checks']),round(result['seconds'],2),flush=True)
    return result


if __name__=='__main__':
    paths=sorted((ROOT/'residual/results').glob('*.json'))
    assert len(paths)==12 and all(load(p)['status']=='complete' for p in paths)
    verify(load(ROOT/'residual/RF_seal.json')['files'])
    write(OUT/'protocol.json',dict(reason='Independent review found missing per-score convergence diagnostics',
        original_outputs_unchanged=True,no_position_optimization=True,source_sha256=sha(__file__),
        expected_score_vectors=96,GPS_used=False))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,paths))
    supplement=load(ROOT/'supplemental_provenance.json')
    verify({p:v['sha256'] for p,v in supplement['files'].items()})
    write(OUT/'summary.json',dict(rows=rows,all_complete=all(r['status']=='complete' for r in rows),
        exact_vectors=sum(len(r['checks']) for r in rows),
        all_checks_pass=all(c['checks_pass'] for r in rows for c in r['checks']),
        causal_ancillary_supplement_reverified=True,initial_freeze_scope_gap_remains_explicit=True))
