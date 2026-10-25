"""One audit CPU: replay only complete case records, then verify the terminal seal."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

from movement_audit import ROOT, check_frozen_inputs, read, sha, write_new

HERE = Path(__file__).resolve().parent


def assemble():
    protocol, _, _, _ = check_frozen_inputs()
    movement = ROOT/'movement'
    seal = read(movement/'scientific_seal.json')
    assert seal['GPS_used'] is False
    for binding in seal['files']:
        assert sha(binding['path']) == binding['sha256'], binding['path']
    partials = [read(HERE/'movement_cases'/(case+'.json')) for case in protocol['cases']]
    decisions = {row['case']:row for row in read(movement/'decisions.json')['cases']}
    cases, jobs, results = {}, [], []
    for partial in partials:
        assert partial['status'] == 'passed'
        assert partial['movement_protocol_sha256'] == sha(movement/'protocol.json')
        assert partial['root_protocol_sha256'] == sha(ROOT/'protocol.json')
        cases.update(partial['cases']); jobs += partial['job_rows']; results += partial['result_bindings']
    assert set(cases) == set(decisions) == set(protocol['cases'])
    for case, rebuilt in cases.items():
        saved = decisions[case]
        assert rebuilt['adopted'] == saved['adopted'], case
        assert rebuilt['endpoint_pair'] == saved['endpoint_pair'], case
        assert saved['policy_source'] == ('sharedRF50' if rebuilt['adopted'] else 'baseline')
        lookup = {(r['seed'],r['arm'],r['predictor'],r['sigma_multiplier']):r for r in saved['aggregate_gains']}
        for row in rebuilt['aggregates']:
            other = lookup[row['seed'],row['arm'],row['predictor'],row['sigma_multiplier']]
            assert (row['gain'] is None) == (other['gain'] is None)
            if row['gain'] is not None:
                assert abs(row['gain']-other['gain']) < 1e-5
    assert len(jobs) == len(results) == 144
    assert len({(r['case'],r['seed'],r['fold']) for r in jobs}) == 144
    for binding in results:
        assert sha(binding['path']) == binding['sha256']
    execution = read(movement/'execution.json')
    assert execution['terminal_records'] == 144 and execution['GPS_used'] is False
    resource = read(movement/'resource_decision.json')
    preflight = read(ROOT/'preflight.json')
    expected_workers = 6 if (len(resource['peak_rss_kib']) == 2 and preflight['allocated_cpu_capacity'] >= 8
        and 6*max(resource['peak_rss_kib'])*1024 < preflight['memory_available_bytes']/2) else 2
    assert resource['workers'] == expected_workers
    assert resource['scientific_outcomes_used'] is False
    assert resource['smoke_jobs'] == protocol['smoke_jobs']
    start = read(movement/'batch_start.json')
    assert start['batch_seconds_cap'] == 2700
    score_rows = []
    for case in protocol['cases']:
        with (HERE/'movement_cases'/(case+'_scores.csv')).open() as stream:
            score_rows += list(csv.DictReader(stream))
    with (HERE/'independent_scores.csv').open('x', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(score_rows[0])); writer.writeheader(); writer.writerows(score_rows)
    output = dict(status='passed', GPS_used=False, no_position_fitting=True,
        movement_protocol_sha256=sha(movement/'protocol.json'), scientific_seal_sha256=sha(movement/'scientific_seal.json'),
        source_sha256=sha(Path(__file__)), cases=cases, job_rows=jobs, result_bindings=results,
        position_fits=sum(r['position_fits'] for r in partials), covariance_vectors=sum(r['covariance_vectors'] for r in partials),
        sensitivity_scores=sum(r['sensitivity_scores'] for r in partials),
        maximum_saved_score_difference=max(r['maximum_saved_score_difference'] for r in partials),
        movement_policy_adopted=sum(row['adopted'] for row in cases.values()),
        terminal_jobs=144, complete_jobs=execution['complete_jobs'], resource_workers=expected_workers,
        execution_seconds=execution['seconds'], policy_decisions_independently_reconstructed=True,
        incomplete_and_nonconverged_cases_retained=True,
        partial_audit_bindings=[dict(case=c,path=str(HERE/'movement_cases'/(c+'.json')),
            sha256=sha(HERE/'movement_cases'/(c+'.json'))) for c in protocol['cases']])
    write_new(HERE/'movement_artifacts.json', output)
    print(json.dumps({k:v for k,v in output.items() if k not in ('cases','job_rows','result_bindings','partial_audit_bindings')}, indent=2), flush=True)


def main():
    protocol = read(ROOT/'movement/protocol.json')
    deadline = time.monotonic()+3600
    for case in protocol['cases']:
        target = HERE/'movement_cases'/(case+'.json')
        if target.exists():
            continue
        paths = [ROOT/'movement/results'/f'{case}_seed{seed}_fold{fold}.json'
                 for seed in protocol['seeds'] for fold in range(3)]
        while not all(path.exists() for path in paths):
            if time.monotonic() > deadline: raise TimeoutError('Audit watcher deadline; no science rerun authorized')
            time.sleep(2)
        log = HERE/(case+'_svd.log')
        with log.open('x') as stream:
            subprocess.run([sys.executable, '-B', str(HERE/'movement_audit.py'), '--case', case],
                stdout=stream, stderr=subprocess.STDOUT, check=True)
        print('independent saved-vector replay complete', case, flush=True)
    while not (ROOT/'movement/scientific_seal.json').exists():
        if time.monotonic() > deadline: raise TimeoutError('No terminal scientific seal before audit deadline')
        time.sleep(2)
    assemble()


if __name__ == '__main__': main()
