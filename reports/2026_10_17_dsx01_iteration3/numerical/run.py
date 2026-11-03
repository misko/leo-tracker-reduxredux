"""One uniform remaining-budget attempt on failed, previously polished pilots."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
sys.path[:0]=[str(REPORTS/'2026_10_16_dsx01_models'),str(REPORTS/'2026_10_16_dsx01_iteration2')]
from common import load_context, endpoint_status, save_json, point_state
from endpoint_polish import polish
from centred import CentredObjective


def main():
    root=HERE.parent/'support/annealing'
    for sid in ['S01','S04']:
        ctx=load_context(sid)
        for path in sorted(root.glob(f'polish_{sid}_*.json')):
            parent=json.loads(path.read_text())
            out=HERE/'results'/path.name
            if out.exists():continue
            if not parent.get('attempted') or parent['audit']['accepted']:continue
            calls=1000-parent['cumulative_evaluations']
            seconds=120-parent['cumulative_active_seconds']
            if calls<2 or seconds<=0:continue
            v,n=np.asarray(parent['vector']),np.asarray(parent['nuisance'])
            original=replace(ctx,fixed_c=parent['arm']=='zero-c',deadline=float('inf'))
            begun=time.monotonic()
            model=CentredObjective(original.model,v,n)
            if abs(model.reference_objective-parent['audit']['training_objective'])>1e-7:
                raise ValueError('Immutable previous endpoint no longer replays')
            context=replace(original,model=model,deadline=time.monotonic()+min(78.,seconds))
            cap=min(134,calls-1)
            result=polish(context,v,n,max_evaluations=cap,max_seconds=min(78.,seconds),expected_objective=0.)
            vv,nn=result['vector'],result['nuisance']
            audit=endpoint_status(original,vv,nn)
            assert model.calls==1+result['diagnostics']['evaluations']
            _,_,best,associated,residual=point_state(original.full_model,vv,nn)
            _,_,old_best,old_associated,_=point_state(original.full_model,v,n)
            record=dict(source_id=sid,arm=parent['arm'],method=parent['method'],
                parent_path=str(path),parent_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(),
                vector=vv,nuisance=nn,diagnostics=result['diagnostics'],audit=audit,
                charged_evaluations=model.calls,cumulative_evaluations=parent['cumulative_evaluations']+model.calls,
                cumulative_active_seconds=parent['cumulative_active_seconds']+time.monotonic()-begun,
                objective_delta_resolved_from_rows=result['diagnostics']['objective'],
                original_absolute_objective_delta=audit['training_objective']-model.reference_objective,
                association_changes=int(np.sum(associated!=old_associated)),
                retained_identity_changes=int(np.sum(associated&old_associated&(best!=old_best))),
                qualification='Same mathematical objective, centred row arithmetic and identical gradients/bounds. Separate supplemental cumulative-active-budget attempt; not the original continuous wall interval. No threshold change.')
            assert record['cumulative_evaluations']<=1000
            out.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(out.with_suffix('.npz'),associated=associated,residual_hz=residual,
                satellite_number=ctx.bank.numbers[best],times_s=ctx.observations.times_s)
            save_json(out,record)
            print(json.dumps(dict(source=sid,arm=parent['arm'],method=parent['method'],
                audit=audit,calls=model.calls,association_changes=record['association_changes'])),flush=True)


if __name__=='__main__':main()
