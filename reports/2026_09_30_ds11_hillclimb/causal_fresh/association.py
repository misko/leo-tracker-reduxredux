"""Diagnose orbit/position versus conditional identity changes on scan31."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

import model
from assess import harness

HERE = Path(__file__).resolve().parent


def main():
    plan_path = harness.BASE/'plan.json'
    identity_path = HERE.parent/'source_balance/catalogue_identities.json'
    old_path = harness.BASE/'runs/31_iid.json'
    fresh_path = HERE/'runs/causal/fresh_31.json'
    plan = json.loads(plan_path.read_text())
    identities = json.loads(identity_path.read_text())['scans']['31']['tracks']
    old = json.loads(old_path.read_text())['selected']
    fresh = json.loads(fresh_path.read_text())['selected']
    docs = model.fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][31]]))
    original = model.build_model(docs, plan['config'], 'original', index=31)
    updated = model.build_model(docs, plan['config'], 'fresh', index=31)
    rows = []
    for i, track in enumerate(docs[0]['tracks']):
        variants = {}
        for label, engine, point in [('original', original.engine, old['x']),
                                     ('fresh_fixed_position', updated.engine, old['x']),
                                     ('fresh_refit', updated.engine, fresh['x'])]:
            current = engine.document['tracks'][i]
            prediction, visible = engine.prediction(current, np.asarray(point))
            train, _, audits, _ = model.fast.profile(current['y'][None, :]-prediction, current['mask'])
            if not all(a['converged'] for a in audits):
                raise RuntimeError('CFO stationarity failure')
            train = np.where(visible, train, -np.inf)
            normal = logsumexp(train)
            slot = int(np.argmax(train))
            variants[label] = dict(norad=identities[track['track_id']]['candidate_norad'][slot],
                                   weight=float(np.exp(train[slot]-normal)),
                                   train=float(normal-np.log(current['catalogue_size'])))
        rows.append(dict(track_id=track['track_id'], receiver_id=track['receiver_id'],
                         rf_hz=track['rf_hz'], variants=variants))
    summary = dict(tracks=len(rows), orbit_only_map_changes=sum(
        r['variants']['original']['norad'] != r['variants']['fresh_fixed_position']['norad'] for r in rows),
        final_map_changes=sum(r['variants']['original']['norad'] != r['variants']['fresh_refit']['norad'] for r in rows))
    paths = [Path(__file__), HERE/'model.py', plan_path, identity_path, old_path, fresh_path,
             Path(updated.metadata['patch_path'])]
    result = dict(schema='ds11-causal-fresh-association-diagnostic/v1', index=31, summary=summary,
                  limitation='Conditional MAP identities only; not independent identification truth.', rows=rows,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'association.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
