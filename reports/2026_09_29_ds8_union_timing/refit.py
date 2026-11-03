"""Joint refit with training-selected per-scan timing initializations."""
import hashlib
import json
import sys
import time
from pathlib import Path

from run import HERE, REPORTS, module, read


def main(arm):
    assert arm in ['old', 'rank']
    started = time.monotonic()
    prior = read(HERE/'results.json')
    for name, digest in prior['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    old = read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new = read(REPORTS/'2026_09_29_rank24_control/plan.json')
    assert old['config'] == new['config']
    inputs = {}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],
                  next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    rows = prior['rows']
    helper = module('budget', REPORTS/'2026_09_29_scan_budget/run.py').helper
    docs = helper.baseline.load_documents(dict(config=old['config'], inputs=[inputs[r['session_id']] for r in rows]))
    model = helper.TrendMixturePosition(docs, old['config'], helper.baseline.Stationary, .2)
    selected = [r['arms'][arm]['selected'] for r in rows]
    assert all(s and s['qualified'] for s in selected)
    position = selected[0]['x'][:2]
    assert all(s['x'][:2] == position for s in selected)
    initial = position + [s['x'][2] for s in selected]
    replay = model.evaluate(initial, gradient=False, held=True)
    assert abs(replay['score']-sum(r['arms'][arm]['training'] for r in rows)) < 1e-7
    assert abs(sum(t['held_log_score'] for t in replay['rows'])-sum(r['arms'][arm]['held'] for r in rows)) < 1e-7
    fit = helper.fit_model(model, initial)
    if fit['qualified']:
        scored = model.evaluate(fit['x'], gradient=False, held=True)
        fit.update(estimate_deg=list(model.models[0].coordinates(fit['x'][:3])),
                   held_score=sum(t['held_log_score'] for t in scored['rows']))
    paths = [HERE/'results.json', HERE/'refit.py', HERE/'REFIT_PROTOCOL.md']
    result = dict(arm=arm, initial=initial, fit=fit, elapsed_seconds=time.monotonic()-started,
                  hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/f'refit_{arm}.json').open('x') as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(arm, fit['qualified'], fit.get('estimate_deg'), result['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
