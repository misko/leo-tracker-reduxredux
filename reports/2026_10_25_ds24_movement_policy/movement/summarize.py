"""Seal all RF-only policy decisions before any geographic evaluation."""
import argparse
import csv
from collections import Counter
from pathlib import Path

from common import ARMS, MODELS, SCALES, binding, digest, load_sealed, read, result_path, write_new
from policy import decide, job_failures


def save_csv(path, rows):
    if not rows:
        return
    with Path(path).open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(root):
    root = Path(root).resolve()
    protocol = load_sealed(root)
    execution = read(root/'execution.json')
    if execution['terminal_records'] != 144:
        raise ValueError('every sealed job needs an explicit terminal record')
    paths = [result_path(root, **job) for job in protocol['jobs']]
    results = [read(path) for path in paths]
    full_data = read(root/'full_data_bindings.json')
    decisions = [decide(case, results, full_data[case]) for case in protocol['cases']]
    write_new(root/'decisions.json', dict(protocol_sha256=digest(root/'protocol.json'), GPS_used=False, cases=decisions))
    aggregates, fold_rows, own_rows, train_rows = [], [], [], []
    for decision in decisions:
        for row in decision['aggregate_gains']:
            aggregates.append({**row, 'fold_gains': repr(row['fold_gains']), 'adopted': decision['adopted']})
    for result in results:
        for arm, analysis in result.get('arms', {}).items():
            identity = {k: result[k] for k in ('case', 'seed', 'fold')}
            for model, fitted in analysis.get('fits', {}).items():
                train_rows.append(dict(**identity, arm=arm, model=model,
                    east_km=fitted['endpoint_east_north_km'][0], north_km=fitted['endpoint_east_north_km'][1],
                    final_phase_change_s=fitted['final_phase_change_s'], final_log_precision_change=fitted['training_final_log_precision_change'],
                    stopped=fitted['history'][-1]['fit']['stopped'], training_objective=fitted['training_objective']))
            if result['status'] != 'complete':
                continue
            for scale in SCALES:
                for predictor in MODELS:
                    a, b = [analysis['crossover'][predictor][m]['scores'][str(scale)] for m in MODELS]
                    fold_rows.append(dict(**identity, arm=arm, predictor=predictor, sigma_multiplier=scale,
                        gain=a['negative_twice_log_density']-b['negative_twice_log_density'],
                        quadratic_gain=a['quadratic']-b['quadratic'], logdet_gain=a['logdet']-b['logdet'],
                        held_dimensions=a['dimensions']))
                a, b = [analysis['crossover'][m][m]['scores'][str(scale)] for m in MODELS]
                own_rows.append(dict(**identity, arm=arm, sigma_multiplier=scale,
                    own_model_gain=a['negative_twice_log_density']-b['negative_twice_log_density'],
                    quadratic_gain=a['quadratic']-b['quadratic'], logdet_gain=a['logdet']-b['logdet']))
    for name, rows in [('aggregate_gains.csv', aggregates), ('fold_gains.csv', fold_rows),
        ('own_model_gains.csv', own_rows), ('training_endpoints.csv', train_rows)]:
        save_csv(root/name, rows)
    vectors = [v for result in results for analysis in result.get('arms', {}).values()
        for predictor in analysis.get('crossover', {}).values() for v in predictor.values()]
    convergence = [dict(case=r['case'], seed=r['seed'], fold=r['fold'], failures=job_failures(r))
        for r in results if job_failures(r)]
    summary = dict(status='RF_decisions_complete', GPS_used=False, development_replication=True,
        cases=24, original_policy_adopted=sum(v['original_adopted'] for v in full_data.values()),
        movement_policy_adopted=sum(d['adopted'] for d in decisions),
        job_status_counts=dict(Counter(r['status'] for r in results)),
        position_fits=sum(len(a.get('fits', {})) for r in results for a in r.get('arms', {}).values()),
        crossover_vectors=len(vectors), noise_scores=sum(len(v['scores']) for v in vectors),
        convergence_or_validity_failures=convergence,
        max_job_seconds=max(r['seconds'] for r in results),
        max_peak_rss_kib=max(r.get('peak_rss_kib', 0) for r in results),
        max_fixed_phase_change_s=max((v['phase_refresh_changes_s'][-1] for v in vectors), default=None),
        max_fixed_gamma_log_precision_change=max((v['final_log_precision_change'] for v in vectors), default=None),
        protocol_sha256=digest(root/'protocol.json'), execution=binding(root/'execution.json'))
    write_new(root/'summary.json', summary)
    scientific_files = list(paths) + [Path(v['artifact']) for v in vectors]
    scientific_files += [root/name for name in ('protocol.json', 'freeze_seal.json', 'source_manifest.json',
        'input_manifest.json', 'full_data_bindings.json', 'decisions.json', 'execution.json', 'summary.json',
        'aggregate_gains.csv', 'fold_gains.csv', 'own_model_gains.csv', 'training_endpoints.csv') if (root/name).exists()]
    load_sealed(root)
    write_new(root/'scientific_seal.json', dict(GPS_used=False, protocol_sha256=digest(root/'protocol.json'),
        files=[binding(path) for path in sorted(scientific_files)]))
    print('sealed RF decisions', summary['movement_policy_adopted'], '/24 adopted', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    summarize(parser.parse_args().root)
