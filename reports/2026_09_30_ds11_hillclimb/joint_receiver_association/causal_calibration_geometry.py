"""Refit donor geometry using only inputs finalized before the earliest target."""
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent.parent
sys.path.insert(0, str(REPORTS / '2026_09_30_ds10_scale_weighting'))
from scaled_model import helper


def available(capture, cutoff):
    return capture['capture_end_utc_ns'] < cutoff and capture['finalized_utc_ns'] < cutoff


def main():
    start = time.monotonic()
    plan_path = REPORTS / '2026_09_30_ds10_scale_weighting/plan.json'
    manifest_path = REPORTS / '2026_09_29_ds10_post_ds9/local/manifest.json'
    inventory_path = HERE / 'acquisition-calibration-inventory.json'
    plan = read(plan_path)
    cutoff = read(inventory_path)['earliest_target_utc_ns']
    captures = {r['session_id']: r for r in read(manifest_path)['captures']}
    indices = [i for i, e in enumerate(plan['inputs']) if available(captures[e['session_id']], cutoff)]
    assert indices == list(range(23))
    entries = [plan['inputs'][i] for i in indices]
    sources = {str(p): digest(p) for p in (plan_path, manifest_path, inventory_path, Path(__file__), HERE / 'CAUSAL_CALIBRATION_PROTOCOL.md', Path(helper.__file__), Path(inspect.getfile(helper.TrendMixturePosition)), Path(inspect.getfile(helper.baseline.Stationary)))}
    seed_panels = []
    seeds = {}
    for name in ('N8_0_h0', 'N8_1_h0'):
        path = REPORTS / f'2026_09_29_ds10_geographic/fits/{name}/result.json'
        result = read(path)
        assert result['selected']['qualified']
        assert all(available(captures[s], cutoff) for s in result['sessions'])
        for p, h in result['hashes'].items():
            assert digest(p) == h, p
        sources[str(path)] = digest(path)
        seed_panels.append(result)
        for j, session in enumerate(result['sessions']):
            seeds.setdefault(session, result['selected']['x'][j + 2])
    initial = np.array(seed_panels[0]['selected']['x'][:2] + [seeds.get(e['session_id'], 0.) for e in entries])
    for entry in entries:
        for a in entry['artifacts']:
            assert digest(a['path']) == a['sha256'].removeprefix('sha256:')
            sources[a['path']] = digest(a['path'])
        obs = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'observations'))
        bank = read(next(a['path'] for a in entry['artifacts'] if a['kind'] == 'candidates' and a['path'].endswith('.json')))
        assert all(p['collected_utc_ns'] < obs['start_utc_ns'] for p in bank['provider_sources'])
    docs = helper.baseline.load_documents(dict(config=plan['config'], inputs=entries))
    assert [d['session_id'] for d in docs] == [e['session_id'] for e in entries]
    model = helper.TrendMixturePosition(docs, plan['config'], helper.baseline.Stationary, .2)
    fit = helper.fit_model(model, initial)
    result = dict(fit=fit, indices=indices, sessions=[e['session_id'] for e in entries], initial=initial.tolist(), cutoff_utc_ns=cutoff, excluded_indices=[23], config=plan['config'], reference_used=False, sources=sources, elapsed_s=time.monotonic() - start)
    with (HERE / 'causal-calibration-geometry.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(dict(qualified=fit['qualified'], score=fit['score'], inputs=len(entries), elapsed_s=result['elapsed_s'], projected_gradient=fit.get('projected_gradient'), gradient_audit=fit.get('gradient_audit')), indent=2), flush=True)


if __name__ == '__main__':
    main()
