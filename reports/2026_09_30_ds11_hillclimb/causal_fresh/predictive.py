"""Evaluate frozen endpoints; fresh-bank CFOs fit training observations only."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

import model
from assess import harness, INDICES

HERE = Path(__file__).resolve().parent


def scores(engine, x):
    train_total = held_total = 0.
    for track in engine.document['tracks']:
        prediction, visible = engine.prediction(track, np.asarray(x))
        train, joint, audits, _ = model.fast.profile(track['y'][None, :]-prediction, track['mask'])
        if not all(a['converged'] for a in audits):
            raise RuntimeError('CFO stationarity failure')
        t = logsumexp(np.where(visible, train, -np.inf))
        j = logsumexp(np.where(visible, joint, -np.inf))
        train_total += float(t-np.log(track['catalogue_size']))
        held_total += float(j-t)
    return dict(train=train_total, held=held_total)


def main():
    plan_path = harness.BASE/'plan.json'
    plan = json.loads(plan_path.read_text())
    paths = [Path(__file__), HERE/'model.py', plan_path]
    rows = []
    for index in INDICES:
        result_path = HERE/'runs/causal'/f'fresh_{index:02d}.json'
        old_path = harness.BASE/'runs'/f'{index:02d}_iid.json'
        fit = json.loads(result_path.read_text())
        if fit['selected'] is None:
            rows.append(dict(index=index, status='unqualified; no endpoint'))
            continue
        old = json.loads(old_path.read_text())['selected']
        docs = model.fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][index]]))
        fresh = model.build_model(docs, plan['config'], 'fresh', index=index)
        at_old = scores(fresh.engine, old['x'])
        at_new = scores(fresh.engine, fit['selected']['x'])
        if abs(at_new['train']-fit['selected']['score']) > 1e-6:
            raise ValueError('fresh training score replay failed')
        rows.append(dict(index=index, fresh_bank_at_iid=at_old, fresh_bank_at_fresh=at_new,
                         original_bank_at_iid=fit['selected']['incumbent_common_iid'],
                         original_bank_at_fresh=fit['selected']['common_iid'],
                         fresh_held_endpoint_gain=at_new['held']-at_old['held']))
        paths.extend([result_path, old_path, Path(fresh.metadata['patch_path'])])
    output = dict(schema='ds11-causal-fresh-fixed-endpoint-prediction/v1', rows=rows,
                  limitation='Held observations share source, orbit and extraction errors with training; predictive gain is not geographic validation.',
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'predictive.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
