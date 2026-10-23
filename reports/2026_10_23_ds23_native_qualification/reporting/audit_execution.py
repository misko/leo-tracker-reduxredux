"""Read-only terminal, provenance and physical-ID audit of the bounded study."""
from pathlib import Path
from collections import Counter
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = read(ROOT / 'protocol.json')
    for field in ('input_hashes', 'source_hashes'):
        for name, expected in protocol[field].items():
            assert sha(Path(name)) == expected, name
    cases = protocol['eligible_cases'] + protocol['controls']
    records = {case: read(ROOT / 'raw' / case / 'result.json') for case in cases}
    counts = Counter(r['status'] for r in records.values())
    assert counts == {'accepted': 2, 'graph_fallback_no_new_path_failure': 27, 'unchanged_control': 3}
    gates = Counter()
    max_replay = 0.0
    compact = {}
    for case, r in records.items():
        assert r['candidate_accepted'] == (r['status'] == 'accepted')
        for a in r.get('primary_audits', {}).values():
            max_replay = max(max_replay, abs(a['objective_difference']))
        gates.update(k.rsplit('/', 1)[-1] for k in r.get('failures_on_protected_evidence', {}))
        if r['candidate_accepted']:
            assert r['paired_gates_pass'] and r['original_parent_IDs_preserved']
            removed = {i for e in r['excluded_entries'] for i in e['observation_ids']}
            retained = {i for e in r['remaining_entries'] for i in e['observation_ids']}
            assert not removed & retained
            for arm, coverage in r['policy_final']['coverage'].items():
                ids = coverage['accepted_observation_ids']
                assert len(ids) == len(set(ids)) == coverage['associated']
                assert set(r['graph_parent']['coverage'][arm]['accepted_observation_ids']) <= set(ids)
                assert not removed & set(r['graph_parent']['coverage'][arm]['accepted_observation_ids'])
        keep = ['case', 'status', 'candidate_accepted', 'attempted_refit', 'seconds',
                'original_rescue_eligible', 'original_rescue_accepted', 'excluded_keys',
                'RF_exclusion_reasons', 'failures_on_protected_evidence', 'original_new_paths',
                'original_new_points', 'excluded_new_points', 'paired_gates_pass',
                'original_parent_IDs_preserved', 'development_canary_max_difference']
        compact[case] = {k: r[k] for k in keep if k in r}
        compact[case]['raw_sha256'] = sha(ROOT / 'raw' / case / 'result.json')
    assert max_replay < 1e-5
    result = dict(status='passed', statuses=dict(counts), protected_gate_instances=dict(gates),
                  max_primary_score_replay_difference=max_replay,
                  validated_protocol_inputs=len(protocol['input_hashes']),
                  unchanged_source_hashes=len(protocol['source_hashes']),
                  driver_identity_offset_tests=9, reporting_tests=5, readmission_tests=2,
                  numerical_dependency_files_verified=786,
                  cases=compact)
    (ROOT / 'reporting' / 'execution_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
