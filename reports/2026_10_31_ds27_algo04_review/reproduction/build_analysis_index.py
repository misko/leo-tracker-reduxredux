"""Seal all DS27 fast inference sources for reporting and native-fragment ranking.

The roster and each method's availability are retained independently. No truth
coordinates, fitted models, or scientific gates enter this bookkeeping step.
"""

import argparse
from pathlib import Path
import sys

from offline_algo04 import DEFAULT_RELEASE, digest, read, write


def build(study, *, validate_v3=None):
    if validate_v3 is None:
        sys.path.insert(0, str(DEFAULT_RELEASE / 'src'))
        from leo.contracts.fast_graph_position_v3 import validate_terminal
        validate_v3 = validate_terminal
    execution = study / 'datasets/DS27.json'
    dataset = read(execution)
    cases = [c for c in dataset['cases'] if c['recording_format'] == 'short_window_iq_recording']
    if len({c['case'] for c in cases}) != len(cases):
        raise ValueError('Duplicate frozen fast case')
    for case in cases:
        if not (study / 'cases' / case['case'] / 'pipeline-receipt.json').is_file():
            raise ValueError('Cannot seal unfinished fast case: ' + case['case'])
    if digest(dataset['manifest_path']) != dataset['manifest_sha256']:
        raise ValueError('Frozen acquisition membership changed')
    hashes = {str(execution): digest(execution), str(Path(dataset['manifest_path'])): dataset['manifest_sha256'],
              str(Path(__file__)): digest(__file__)}
    entries = []

    def phase_reason(value):
        return (value.get('reason') or value.get('failure')
                or (value.get('terminal') or {}).get('reason'))

    def bound(row, label, path):
        row[label + '_path'] = str(path)
        row[label + '_sha256'] = hashes[str(path)] = digest(path)

    for case in cases:
        folder = study / 'cases' / case['case']
        pipeline_path = folder / 'pipeline-receipt.json'
        pipeline = read(pipeline_path)
        hashes[str(pipeline_path)] = digest(pipeline_path)
        phases = {}
        for phase, path in (('ALGO02', folder / 'baseline-receipt.json'),
                            ('ALGO03', folder / 'candidate-receipt.json'),
                            ('ALGO04', folder / 'candidate-v3/receipt.json')):
            if path.exists():
                phases[phase] = read(path)
                hashes[str(path)] = digest(path)
            else:
                phases[phase] = dict(state='unavailable', reason='stage_receipt_absent')
        row = dict(case=case['case'], recording_id=case['recording_id'],
                   run_id=(case.get('production_job') or {}).get('run_id'),
                   input_sha256=(case.get('input') or {}).get('sha256'),
                   state=pipeline['state'], method_states={k: v['state'] for k, v in phases.items()},
                   method_reasons={k: phase_reason(v) for k, v in phases.items()},
                   algo03_recovery_path=str(folder / 'candidate-v2/recovery'),
                   algo04_recovery_path=str(folder / 'candidate-v3/recovery'),
                   pipeline_receipt_path=str(pipeline_path), pipeline_receipt_sha256=digest(pipeline_path))
        baseline = phases['ALGO02']
        baseline_path = folder / 'algo02/terminal.json'
        if baseline_path.is_file():
            bound(row, 'baseline_terminal', baseline_path)
        elif isinstance(baseline.get('terminal'), dict):
            # Reused public ALGO02 receipts embed its exact terminal value.
            # Materialize that value for method-specific coverage, binding its
            # receipt and source snapshot separately in the final seal.
            baseline_path = study / 'index-method-terminals' / case['case'] / 'baseline.json'
            if baseline_path.exists():
                if read(baseline_path) != baseline['terminal']:
                    raise ValueError('Materialized baseline differs from its source receipt')
            else:
                write(baseline_path, baseline['terminal'])
            bound(row, 'baseline_terminal', baseline_path)
        candidate_path = folder / 'candidate-v2/terminal.json'
        if candidate_path.is_file():
            bound(row, 'candidate_terminal', candidate_path)
        family_log = folder / 'algo02/family.log'
        if baseline['state'] == 'failed' and family_log.is_file():
            text = family_log.read_text()
            errors = [line.strip() for line in text.splitlines()
                      if line.startswith(('ValueError:', 'RuntimeError:', 'TimeoutError:'))]
            if errors:
                row['underlying_baseline_failures'] = list(dict.fromkeys(errors))
                bound(row, 'baseline_failure_log', family_log)
                if 'family-excluded calibration phase did not converge' in text:
                    row['underlying_baseline_gate'] = dict(maximum_phase_change_s=.01,
                        criterion='family-excluded calibration phase must converge before its position output exists')
        if row['state'] != 'complete':
            row['reason'] = next((phase_reason(phases[p])
                                  for p in ('ALGO02', 'ALGO03', 'ALGO04')
                                  if phases[p]['state'] != 'complete'), pipeline.get('failure'))
            if row.get('underlying_baseline_failures'):
                row['wrapper_failure'] = row['reason']
                row['reason'] = '; '.join(row['underlying_baseline_failures'])
            entries.append(row)
            continue
        terminal_path = folder / 'candidate-v3/terminal.json'
        terminal = read(terminal_path)
        validate_v3(terminal, input_sha256=row['input_sha256'])
        inference = folder / 'candidate-v3/inference-seal.json'
        seal = read(inference)
        if seal['output_hashes'].get(str(terminal_path)) != digest(terminal_path):
            raise ValueError('ALGO04 terminal differs from its inference seal: ' + case['case'])
        hashes[str(inference)] = digest(inference)
        bound(row, 'terminal', terminal_path)
        row['decision'] = terminal['decision']
        recoveries = [folder / 'candidate-v3/recovery', folder / 'candidate-v2/recovery']
        snapshot = next((r / 'snapshot/inference/SCAN' for r in recoveries
                         if (r / 'snapshot/inference/SCAN/tracks.json').is_file()
                         and (r / 'snapshot/inference/SCAN/observations.json').is_file()), None)
        if snapshot is None:
            raise ValueError('Complete inference lacks original native graph: ' + case['case'])
        bound(row, 'tracks', snapshot / 'tracks.json')
        bound(row, 'observations', snapshot / 'observations.json')
        inventories = [p for r in recoveries for p in sorted((r / 'all-large-track-recovery').glob('*/inventory.json'))]
        if inventories:
            inv_path = inventories[0]
            row['identities'] = read(inv_path)['job']['identities']
            bound(row, 'inventory', inv_path)
        else:
            job_path = next((r / 'inventory-job.json' for r in recoveries if (r / 'inventory-job.json').is_file()), None)
            if job_path is None:
                raise ValueError('No exact inventory identity basis for native tracks: ' + case['case'])
            row['identities'] = read(job_path)['identities']
            bound(row, 'inventory_job', job_path)
        if not row['identities'] or len(set(row['identities'])) != len(row['identities']):
            raise ValueError('Invalid native graph identity basis')
        entries.append(row)
    index = study / 'analysis-index.json'
    write(index, dict(schema='ds27-ranking-input/v1', fixture_only=False,
                      cases=entries, all_fast_members_retained=True, no_GPS=True))
    write(study / 'analysis-seal.json', dict(
        analysis_index_sha256=digest(index), dataset_execution_manifest_sha256=digest(execution),
        dataset_manifest_sha256=digest(dataset['manifest_path']), source_hashes=hashes,
        fast_cases=[c['case'] for c in cases], all_fast_terminal=True,
        no_GPS=True, production_changed=False))
    return dict(cases=len(entries), complete=sum(r['state'] == 'complete' for r in entries),
                unavailable=sum(r['state'] == 'unavailable' for r in entries),
                failed=sum(r['state'] == 'failed' for r in entries),
                analysis_index=str(index), analysis_index_sha256=digest(index))


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=Path(__file__).resolve().parent)
    print(json.dumps(build(parser.parse_args().study.resolve())), flush=True)
