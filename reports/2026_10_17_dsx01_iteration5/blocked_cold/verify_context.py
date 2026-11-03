"""No-fit verification of reusable training context and CFO-blind prediction port."""
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from numpy.testing import assert_array_equal
from training_context import load_training_context,predict_original
from derive_blocks import digest
from leo.contracts.regional_position import PositionObservations

HERE=Path(__file__).resolve().parent
ATTEMPT=HERE/'S03-block20-parity0'


def run():
    ctx=load_training_context();v=ctx.vector.copy();n=ctx.nuisance.copy()
    rows=[json.loads(line) for line in (HERE.parents[1]/'2026_10_16_dsx01_fast_association_losses'/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']=='S03']
    metadata=PositionObservations(tuple(r['observation_id'] for r in rows),np.array([r['time_s'] for r in rows]),
        np.zeros(len(rows)),np.array([r['actual_rf_hz'] for r in rows]),np.array([r['receiver']-1 for r in rows]),
        np.array([r['channel'] for r in rows]),np.ones(len(rows)))
    first=predict_original(ctx,v,n,metadata)
    with np.load(ATTEMPT/'predictions.npz') as saved:
        for name,value in first.items():assert_array_equal(value,saved[name])
        held=saved['held_mask'].copy()
    changed=metadata.measured_hz.copy();changed[held]=123456.789*np.arange(1,held.sum()+1)
    second=predict_original(ctx,v,n,replace(metadata,measured_hz=changed))
    for name,value in first.items():assert_array_equal(value,second[name])
    assert_array_equal(v,ctx.vector);assert_array_equal(n,ctx.nuisance)
    result=dict(passed=True,training_observations=len(ctx.observations.times_s),selected_ids=ctx.bank.numbers.tolist(),
        observations=len(metadata.times_s),held_observations=int(held.sum()),
        exact_saved_predictions_from_reusable_context=True,held_cfo_invariance_of_prediction_port=True,
        seed_and_nuisance_unmutated=True,source=ctx.source,
        code_sha256={name:digest((HERE/name).read_bytes()) for name in ['training_context.py','verify_context.py']},
        qualification='No fit. Original shared prediction port; future changed-model residual terms require an explicit adapter and separate budgets.')
    with (ATTEMPT/'context-verification.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':run()
