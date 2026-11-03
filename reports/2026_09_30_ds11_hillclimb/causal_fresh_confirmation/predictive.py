"""Frozen-endpoint predictive scores and the updated candidate's support."""
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

import confirmation_model as model
from run import INDICES

HERE = Path(__file__).resolve().parent


def score(engine, point, side):
    train_total = held_total = mass = 0.
    map_count = occurrences = 0
    for track in engine.document['tracks']:
        prediction, visible = engine.prediction(track, np.asarray(point))
        train, joint, audits, _ = model.core.fast.profile(track['y'][None, :]-prediction, track['mask'])
        if not all(a['converged'] for a in audits):
            raise RuntimeError('CFO stationarity failed')
        train = np.where(visible, train, -np.inf)
        normal = logsumexp(train)
        train_total += float(normal-np.log(track['catalogue_size']))
        held_total += float(logsumexp(np.where(visible, joint, -np.inf))-normal)
        norads = np.asarray(side['tracks'][track['track_id']]['candidate_norad'])
        chosen = np.flatnonzero(norads == 53505)
        if len(chosen):
            occurrences += 1
            mass += float(np.exp(train[chosen[0]]-normal))
            map_count += int(norads[int(np.argmax(train))] == 53505)
    return dict(train=train_total, held=held_total, candidate_53505_occurrences=occurrences,
                candidate_53505_probability_sum=mass, candidate_53505_map_tracks=map_count)


def main():
    plan_path = HERE/'plan.json'
    side_path = HERE/'catalogue_identities.json'
    plan = json.loads(plan_path.read_text())
    identities = json.loads(side_path.read_text())
    rows = []
    paths = [Path(__file__), HERE/'confirmation_model.py', plan_path, side_path, HERE/'patch-audit.json']
    for slot, entry in enumerate(plan['inputs']):
        index = entry['full_manifest_index']
        assert index in INDICES
        old_path = HERE/'runs'/f'original_{index:02d}.json'
        new_path = HERE/'runs'/f'fresh_{index:02d}.json'
        old = json.loads(old_path.read_text())['selected']
        new = json.loads(new_path.read_text())['selected']
        if old is None or new is None:
            raise ValueError('matched qualified endpoints required for this diagnostic')
        docs = model.core.fast.load_documents(dict(config=plan['config'], inputs=[entry]))
        original = model.build_model(docs, plan['config'], 'original', index)
        fresh = model.build_model(docs, plan['config'], 'fresh', index)
        variants = {}
        for name, engine, point in [('original_bank_at_original', original.engine, old['x']),
                                    ('original_bank_at_fresh', original.engine, new['x']),
                                    ('fresh_bank_at_original', fresh.engine, old['x']),
                                    ('fresh_bank_at_fresh', fresh.engine, new['x'])]:
            variants[name] = score(engine, point, identities['scans'][str(slot)])
        assert abs(variants['original_bank_at_original']['train']-old['score']) < 1e-6
        assert abs(variants['fresh_bank_at_fresh']['train']-new['score']) < 1e-6
        rows.append(dict(index=index, scores=variants))
        paths.extend([old_path, new_path, Path(fresh.metadata['patch_path'])])
    result = dict(schema='ds11-causal-confirmation-predictive/v1', rows=rows,
                  limitation='Training-conditional candidate probabilities are not verified identity; held points share source errors.',
                  source_sha256={str(p):model.core.digest(p) for p in paths})
    with (HERE/'predictive.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(next(r for r in rows if r['index'] == 75), indent=2))


if __name__ == '__main__':
    main()
