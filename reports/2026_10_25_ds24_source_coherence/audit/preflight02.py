"""Narrow independent audit of the authorized metadata-port repair."""
import ast
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'scientific'
RUN = SCI / 'run02'
sys.path.insert(0, str(SCI))
import coherence02 as c

read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start = time.monotonic()
    checks = []
    def check(name, ok, **detail):
        checks.append(dict(name=name, passed=bool(ok), **detail))
    protocol = read(RUN / 'protocol.json')
    digest = sha(RUN / 'protocol.json')
    check('exact revision02 freeze and original source/input bindings',
          digest == '6b46e3b99c0239b93bf19f9923f399df39055830826bae3290113fc6d768c80e' and
          read(RUN / 'protocol_seal.json')['protocol_sha256'] == digest and
          all(sha(path) == value for path, value in protocol['source_input_hashes'].items()))
    old = ast.parse((SCI / 'coherence.py').read_text())
    new = ast.parse((SCI / 'coherence02.py').read_text())
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
    unchanged = set(old_functions) - {'load', 'verify', 'freeze', 'run'}
    check('all mathematical kernels, models, quadrature, envelopes and job logic unchanged',
          all(ast.dump(old_functions[name]) == ast.dump(new_functions[name]) for name in unchanged),
          unchanged_functions=sorted(unchanged))
    old_load = ast.get_source_segment((SCI / 'coherence.py').read_text(), old_functions['load'])
    new_load = ast.get_source_segment((SCI / 'coherence02.py').read_text(), new_functions['load'])
    check('only load change is the correct metadata module attribute',
          old_load.replace('p.w.OLD', 'p.OLD') == new_load and
          c.p.OLD == Path('/srv/bulk/leo/research/ds24-rx2-witness-r01/scientific') and
          not hasattr(c.p.w, 'OLD') and (c.p.OLD / 'owner1/metadata.json').exists())
    initial = read(SCI / 'execution.json')
    initial_seal = read(SCI / 'RF_seal.json')
    check('original failed attempt immutable and before every integral',
          all(sha(path) == value for path, value in initial_seal['files'].items()) and
          len(initial['arms']) == 2 and all(not row['completed_quadrature_models'] and
          "has no attribute 'OLD'" in row['error'] for row in initial['arms']))
    smoke = read(RUN / 'load_smoke.json')
    check('actual two-arm input load smoke passes, no scientific density evaluated',
          smoke['all_passed'] and smoke['source_sha256'] == sha(SCI / 'coherence02.py') and
          {row['arm'] for row in smoke['checks']} == {'c0', 'fitted_c'} and
          all(row['passed'] and (row['native_IDs'], row['D_IDs'], row['W_IDs']) == (100, 57, 43)
              for row in smoke['checks']) and smoke['density_evaluations'] == smoke['quadrature_evaluations'] == 0)
    spent = initial['scientific_seconds'] + smoke['scientific_worker_seconds']
    remaining = 600 - spent
    check('failed attempt and both actual load smoke calls charged without budget reset',
          initial['scientific_seconds'] == 4.737606174312532 and
          smoke['scientific_worker_seconds'] == 4.404138068668544 and
          protocol['remaining_worker_seconds'] == remaining and
          protocol['worker_deadline_seconds'] == remaining / 2 and
          protocol['scientific_seconds'] == 600 and protocol['workers'] == 2 and
          protocol['scientific_retries'] == 0 and not (RUN / 'execution_started.json').exists(),
          prior_failed_seconds=initial['scientific_seconds'], smoke_seconds=smoke['scientific_worker_seconds'],
          remaining_seconds=remaining)
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(SCI / 'test_coherence02.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('eleven owned tests independently rerun', status == 0)
    check('frozen sources and inputs unchanged after tests',
          all(sha(path) == value for path, value in protocol['source_input_hashes'].items()))
    seconds = time.monotonic() - start
    cumulative = seconds + read(HERE / 'preflight.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(row['passed'] for row in checks) and cumulative <= 180,
        protocol_sha256=digest, checks=checks, seconds=seconds, cumulative_audit_seconds=cumulative,
        audit_cap_seconds=180, source_sha256=sha(__file__), new_corpus_scores=0,
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        preserved_original_preflight_sha256=sha(HERE / 'preflight.json'),
        interpretation='Authorized pre-integral metadata-port repair only; no scientific model, prior, split, criterion or budget change.')
    with (HERE / 'preflight02.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], protocol_sha256=digest,
        failed=[row for row in checks if not row['passed']], cumulative_audit_seconds=cumulative)))


if __name__ == '__main__':
    main()
