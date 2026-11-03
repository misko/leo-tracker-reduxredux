import hashlib
import json
import math
import time
from pathlib import Path

from tools.rx_paired_state_cv import prepare_fold, evaluate, controlled
from tools.rx_paired_state_model import calibration_score


def select_time(scores):
    if not scores or any(not math.isfinite(x['score']) for x in scores):
        raise ValueError('finite nonempty scores required')
    return max(scores, key=lambda x: (x['score'], -x['tau_s']))['tau_s']


def main():
    start = time.monotonic()
    here = Path(__file__).resolve().parent
    old = here.parent / '2026_09_28_rx_paired_state_cv'
    dataset = here.parent / '2026_09_28_rx_geometry_association/dataset.json'
    payload = dataset.read_bytes()
    document = json.loads(payload)
    sources = [dataset, here/'PROTOCOL.md', Path(__file__)]
    folds = []
    for i in range(6):
        path = old / f'fold-{i}.json'
        sources.append(path)
        saved = json.loads(path.read_text())
        assert saved['dataset_sha256'] == hashlib.sha256(payload).hexdigest()
        train, held, receipt = prepare_fold(document, i)
        for key in ('training_source_window_ids', 'held_source_window_ids'):
            assert receipt[key] == saved[key]
        row = {'held_session': receipt['held_session'], 'arms': {}, 'controls': {}}
        for arm in ('P', 'U', 'O'):
            original = saved['fits'][arm]['selected']
            replay = evaluate(held, original)['roles']
            for role in replay:
                assert abs(replay[role]['relative_log_score_per_window'] -
                           saved['evaluations'][arm]['roles'][role]['relative_log_score_per_window']) < 1e-8
            grid = [{'tau_s': tau, 'score': calibration_score(
                train, original['beta'], original['occupancy'], tau)}
                    for tau in (1., 10., 30., 100., 300.)]
            selected = {**original, 'tau_s': select_time(grid)}
            row['arms'][arm] = {'grid': grid, 'selected_tau_s': selected['tau_s'],
                                'original_tau_s': original['tau_s'], 'original': replay,
                                'roles': evaluate(held, selected)['roles']}
            if arm == 'O':
                for name in ('O_swap', 'O_reverse', 'O_permute'):
                    row['controls'][name] = evaluate(controlled(held, name), selected)['roles']
        folds.append(row)
    summary = {}
    for role in ('reception', 'held_frequency'):
        def value(row, arm):
            entry = row['arms'][arm]['roles'] if arm in row['arms'] else row['controls'][arm]
            return entry[role]['relative_log_score_per_window']
        contrasts = {}
        for left, right in [('O','U'), ('O','P'), ('O','O_swap'), ('O','O_reverse'), ('O','O_permute')]:
            values = [value(r,left)-value(r,right) for r in folds]
            contrasts[f'{left}-{right}'] = {'mean': math.fsum(values)/6,
                'positive_over_1e-6': sum(v > 1e-6 for v in values), 'values': values}
        summary[role] = contrasts
    sources.extend(Path.cwd()/'tools'/name for name in
                   ('rx_paired_state_model.py', 'rx_paired_state_cv.py', 'rx_presence_geometry.py'))
    result = {'folds': folds, 'summary': summary, 'elapsed_s': time.monotonic()-start,
              'source_sha256': {str(p.relative_to(Path.cwd())): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sources}}
    with (here/'results.json').open('x') as f:
        json.dump(result,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
