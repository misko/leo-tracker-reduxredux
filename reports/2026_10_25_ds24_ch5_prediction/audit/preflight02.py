"""Narrow Path-port repair review; first execution and budget stay preserved."""
import ast
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
OWN = HERE.parent / 'prediction'
SCI = OWN / 'run02'
sys.path.insert(0, str(OWN))


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def functions(path):
    return {node.name: node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)}


def main():
    output = HERE / 'preflight02.json'
    if output.exists():
        raise FileExistsError('preserve receipts')
    began = time.monotonic()
    p = read(SCI / 'protocol.json')
    digest = sha(SCI / 'protocol.json')
    checks = []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    first = read(OWN / 'RF_seal.json')
    old_execution = read(OWN / 'execution.json')
    check('failed original scientific outputs and sources all immutable', all(sha(path) == h for path, h in first['files'].items()))
    failures = [q for arm in old_execution['arms'] for q in arm['pairs']]
    check('original four failures are path-port only and precede every evidence integral',
          len(failures) == 4 and all('PosixPath' in q['error'] and "name+'_support.json'" in q['traceback'] for q in failures)
          and not list(OWN.glob('*/*_evidence.json')) and not list(OWN.glob('*/*_primary_checkpoint.json')))
    old_functions, new_functions = functions(OWN / 'prediction.py'), functions(OWN / 'prediction02.py')
    unchanged = set(old_functions) - {'freeze', 'verify', 'run', 'evidence'}
    identical = all(ast.dump(old_functions[name]) == ast.dump(new_functions[name]) for name in unchanged)
    evidence = new_functions['evidence']
    first_statement = ast.dump(evidence.body[0])
    evidence.body = evidence.body[1:]
    check('all scientific functions identical except exact name=str(name) output-port coercion',
          identical and ast.dump(old_functions['evidence']) == ast.dump(evidence) and
          first_statement == ast.dump(ast.parse('name=str(name)').body[0]), unchanged_functions=sorted(unchanged))
    spent = old_execution['scientific_seconds']
    check('original exact science time deducted; no budget reset',
          spent == p['budget']['prior_harness_worker_seconds'] == 7.320185383781791 and
          p['budget']['total_worker_seconds'] == 600 and p['budget']['remaining_worker_seconds'] == 600 - spent and
          p['budget']['each_worker_wall_seconds'] == (600 - spent) / 2 and
          p['preserved_failed_protocol_sha256'] == sha(OWN / 'protocol.json'))
    check('root path-only repair authorization bound; no second execution yet',
          str(HERE.parent / 'HARNESS_REPAIR_AUTHORIZATION.md') in p['source_input_hashes'] and
          not (SCI / 'execution_started.json').exists() and p['position_fits'] == p['GPS_used'] == 0)
    check('revised exact protocol and every original/revised binding verified',
          digest == read(SCI / 'protocol_seal.json')['protocol_sha256'] and
          all(sha(path) == h for path, h in p['source_input_hashes'].items()))
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(OWN / 'test_prediction02.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('eight tests independently rerun including actual Path evidence-port regression', status == 0)
    check('sources remain frozen after pure tests', all(sha(path) == h for path, h in p['source_input_hashes'].items()))
    elapsed = time.monotonic() - began
    prior = read(HERE / 'preflight.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(q['passed'] for q in checks), protocol_sha256=digest,
        original_protocol_sha256=sha(OWN / 'protocol.json'), original_RF_seal_sha256=sha(OWN / 'RF_seal.json'),
        checks=checks, seconds=elapsed, cumulative_audit_seconds=prior + elapsed, audit_cap_seconds=180,
        source_sha256=sha(__file__), corpus_propagation_calls=0, new_corpus_scores=0,
        position_fits=0, geographic_truth_read=False,
        authorization='root path-only repair authorization; original observations/models/criteria unchanged, exact original science time charged')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], protocol_sha256=digest,
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], failed=[q for q in checks if not q['passed']])))


if __name__ == '__main__':
    main()
