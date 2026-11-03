"""Compare timing basins at both frozen DS8 N40 endpoints."""
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started = time.monotonic()
    sources = [REPORTS/'2026_09_29_ds8_union40'/f'{arm}.json' for arm in ['old', 'rank']]
    fits = {arm: read(path) for arm, path in zip(['old', 'rank'], sources)}
    hashes = {}
    for result in fits.values():
        for name, digest in result['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
            hashes[name] = digest
    prior = read(REPORTS/'2026_09_29_ds8_sampling_diagnostic/results.json')
    for name, digest in prior['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
        hashes[name] = digest
    old = read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new = read(REPORTS/'2026_09_29_rank24_control/plan.json')
    assert old['config'] == new['config']
    inputs = {}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],
                  next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']: s['input'] for s in scans})
    sessions = fits['old']['sessions']
    assert sessions == fits['rank']['sessions'] and len(set(sessions)) == 40
    budget = module('budget', REPORTS/'2026_09_29_scan_budget/run.py')
    helper = budget.helper
    timing_path = REPORTS/'2026_09_29_disjoint_frozen_association/run.py'
    timing = module('timing_control', timing_path).timing_fit
    docs = helper.baseline.load_documents(dict(config=old['config'], inputs=[inputs[s] for s in sessions]))
    grid = np.array(old['config']['timing_grid_s'])
    rows = []
    for i, doc in enumerate(docs):
        assert doc['session_id'] == sessions[i]
        model = helper.TrendMixturePosition([doc], old['config'], helper.baseline.Stationary, .2)
        arms = {}
        posteriors = {}
        for arm, other in [('old', 'rank'), ('rank', 'old')]:
            x = fits[arm]['fit']['x']
            position = np.array(x[:2])
            original = model.evaluate([*position, x[i+2]], gradient=False, held=True)
            scores, _ = budget.training_scores(model, position, grid)
            starts = [('own', x[i+2]), ('other', fits[other]['fit']['x'][i+2]),
                      ('grid', float(grid[int(np.argmax(scores))]))]
            attempts = [dict(timing(model, position, [tau]), start=label, initial_tau_s=tau)
                        for label, tau in starts]
            valid = [a for a in attempts if a['qualified']]
            selected = max(valid, key=lambda a:a['score']) if valid else None
            data = dict(starts=attempts, selected=selected, original_training=original['score'],
                        original_held=sum(r['held_log_score'] for r in original['rows']))
            if selected:
                assert selected['x'][:2] == position.tolist()
                scored = model.evaluate(selected['x'], gradient=False, held=True)
                pairs = list(zip(original['rows'], scored['rows'], strict=True))
                assert all(a['track_id']==b['track_id'] for a,b in pairs)
                data.update(training=scored['score'], held=sum(r['held_log_score'] for r in scored['rows']),
                            tau_change_s=selected['x'][2]-x[i+2],
                            candidate_changes=sum(int(np.argmax(a['weights_given_signal']))!=int(np.argmax(b['weights_given_signal'])) for a,b in pairs))
                posteriors[arm] = scored['rows']
            arms[arm] = data
        row = dict(session_id=sessions[i], arms=arms, tracks=len(doc['tracks']))
        if len(posteriors)==2:
            pairs = list(zip(posteriors['old'], posteriors['rank'], strict=True))
            assert all(a['track_id']==b['track_id'] for a,b in pairs)
            row['endpoint_candidate_changes'] = sum(int(np.argmax(a['weights_given_signal']))!=int(np.argmax(b['weights_given_signal'])) for a,b in pairs)
        rows.append(row)
    summary = {}
    for arm in ['old', 'rank']:
        for key, fit_key in [('original_training', 'score'), ('original_held', 'held_score')]:
            assert abs(sum(r['arms'][arm][key] for r in rows)-fits[arm]['fit'][fit_key]) < 1e-7
        valid = [r['arms'][arm] for r in rows if r['arms'][arm]['selected']]
        summary[arm] = dict(qualified=len(valid), training_gain=sum(a['training']-a['original_training'] for a in valid),
                           held_gain=sum(a['held']-a['original_held'] for a in valid),
                           candidate_changes=sum(a['candidate_changes'] for a in valid),
                           max_timing_change_s=max(abs(a['tau_change_s']) for a in valid))
    for path in sources+[HERE/'run.py', HERE/'PROTOCOL.md', timing_path]:
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(rows=rows, summary=summary, hashes=hashes, elapsed_seconds=time.monotonic()-started)
    with (HERE/'results.json').open('x') as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(json.dumps(dict(summary=summary, elapsed_seconds=result['elapsed_seconds']), indent=2))


if __name__ == '__main__':
    main()
