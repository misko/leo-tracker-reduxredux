import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

from frozen_model import FrozenAssociation

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(p):
    return json.loads(p.read_text())


def main(ds):
    started = time.monotonic()
    for name, h in read(HERE / 'manifest.json')['hashes'].items():
        assert hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() == h, name
    spec = importlib.util.spec_from_file_location('receiver', REPORTS / '2026_09_29_receiver_holdout/run.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest = read(REPORTS / '2026_09_29_scan_budget/manifest.json')
    source = next(s for s in manifest['sets'] if s['dataset'] == ds and s['count'] == 24)
    docs = helper.baseline.load_documents(dict(config=manifest['config'], inputs=[s['input'] for s in source['scans']]))
    by_id = {d['session_id']: d for d in docs}
    prior = read(REPORTS / f'2026_09_29_scan_budget/{ds}_n24_0.json')
    pool_x = prior['selected']['x']
    timing = dict(zip(prior['sessions'], pool_x[2:], strict=True))
    panels = []
    for family, suffixes in [('contiguous', ['early', 'middle', 'late']), ('balanced', [0, 1, 2])]:
        for suffix in suffixes:
            old = read(REPORTS / f'2026_09_29_time_balanced_scans/grid_{ds}_{family}_{suffix}.json')
            subset = [by_id[s] for s in old['sessions']]
            original = helper.TrendMixturePosition(subset, manifest['config'], helper.baseline.Stationary, 0.2)
            donor = np.array([*pool_x[:2], *[timing[s] for s in old['sessions']]])
            frozen = FrozenAssociation(original, donor)
            a, b = original.evaluate(donor), frozen.evaluate(donor)
            score_audit = abs(a['score']-b['score'])
            gradient_audit = float(np.max(np.abs(a['gradient']-b['gradient'])))
            assert max(score_audit, gradient_audit) < 1e-7
            assert frozen.evaluate(old['selected']['x'], gradient=False)['score'] <= old['selected']['score'] + 1e-7
            starts = []
            for label, x in [('panel', old['selected']['x']), ('donor', donor)]:
                try:
                    fit = dict(helper.fit_model(frozen, x), start=label)
                except (ValueError, AssertionError) as exc:
                    fit = dict(qualified=False, start=label, exception=repr(exc))
                starts.append(fit)
            valid = [s for s in starts if s['qualified']]
            selected = max(valid, key=lambda s: s['score']) if valid else None
            result = dict(dataset=ds, family=family, panel=str(suffix), starts=starts, selected=selected, donor_score_audit=score_audit, donor_gradient_audit=gradient_audit, old_estimate_deg=old['selected']['estimate_deg'])
            if selected:
                selected['estimate_deg'] = list(original.models[0].coordinates(selected['x'][:3]))
                scores = {}
                for label, x in [('panel', old['selected']['x']), ('donor', donor), ('frozen_fit', selected['x'])]:
                    out = original.evaluate(x, gradient=False, held=True)
                    scores[label] = dict(training=out['score'], held=sum(r['held_log_score'] for r in out['rows']))
                assert selected['score'] <= scores['frozen_fit']['training'] + 1e-7
                result['original_model_scores'] = scores
                result['surrogate_gain_over_donor'] = selected['score'] - b['score']
            panels.append(result)
            with (HERE / f'{ds}_{family}_{suffix}.json').open('x') as out:
                json.dump(result, out, indent=2, allow_nan=False)
    with (HERE / f'{ds}.json').open('x') as out:
        json.dump(dict(panels=panels, elapsed_seconds=time.monotonic()-started), out, indent=2, allow_nan=False)
    print(ds, time.monotonic()-started, flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
