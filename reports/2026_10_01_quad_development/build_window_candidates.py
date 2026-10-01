"""Freeze accepted candidate coordinates without accessing reference errors."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent
RECOVERED = {'DS9-B05-S2', 'DS9-B05-S3', 'DS11-B04-S1'}


def main():
    output = HERE/'window-candidate-manifest-v1.json'
    if output.exists(): raise FileExistsError(output)
    inputs, frozen = {}, {}

    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value

    def merge(mapping):
        for name, expected in mapping.items():
            assert name not in frozen or frozen[name] == expected
            frozen[name] = expected

    selection = read(HERE/'selection.json')
    replay = read(HERE/'first-start-complete-v1.json')
    extension = read(HERE/'iteration96-summary-v1.json')
    for summary in (replay, extension):
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'): merge(summary[key])
    original = {r['unit']: r for r in replay['rows']}
    assert {u for u, r in original.items() if not r['first']['accepted']} == RECOVERED
    extended = {r['unit']: r for r in extension['rows']}
    assert all(extended[u]['arms']['96']['accepted'] and extended[u]['policy_checks_pass'] for u in RECOVERED)
    blocks = []
    for block in selection['blocks']:
        units = [u for u in selection['evaluation_units'] if u['block_id'] == block['block_id']]
        candidates = []
        for policy in ('first', 'original_winner'):
            for unit in units:
                name = unit['unit_id']
                if policy == 'first':
                    folder = (HERE/'iteration96-v1'/name if name in RECOVERED else
                              HERE/'first-start-replay-v1'/unit['block_id']/name)
                else:
                    if not original[name]['baseline']['accepted']: continue
                    folder = HERE/'independent-v2'/unit['block_id']
                path = folder/(name+'.json'); receipt = read(path)
                evaluation = read(folder/'evaluation.json')
                audit_rows = [r for r in evaluation['rows'] if r['unit'] == name]
                assert len(audit_rows) == 1 and audit_rows[0]['accepted']
                assert audit_rows[0]['receipt_sha256'] == digest(path)
                assert receipt['status'] == 'converged_local_mode' and receipt['best']['converged']
                assert receipt['binding'] == unit
                assert receipt['model'] == 'shared_position_independent_scan_nuisances'
                assert receipt['config']['height_m_msl'] == 30.48 and receipt['config']['prior_radius_km'] == 250
                if policy == 'first': assert receipt['best']['seed_index'] == 0
                point = np.asarray(receipt['best']['mean'][:2], dtype=float)
                assert np.isfinite(point).all() and np.linalg.norm(point) <= 250
                merge(receipt['source_sha256']); merge(receipt['inputs'])
                merge({receipt['height']['grid_path']: receipt['height']['grid_sha256']})
                candidates.append(dict(id=name+'|'+policy, unit=name, block=unit['block_id'],
                    policy=policy, scans=unit['scans'], size=unit['size'], point_km=point.tolist(),
                    receipt_path=str(path), receipt_sha256=digest(path), audit_path=str(folder/'evaluation.json'),
                    origin_iteration_cap=receipt['config']['max_iterations']))
        assert sum(c['policy'] == 'first' for c in candidates) == 7
        blocks.append(dict(block=block['block_id'], dataset=block['dataset'], scans=block['scans'],
                           targets=units, candidates=candidates))
    assert len(blocks) == 16 and sum(len(b['candidates']) for b in blocks) == 219
    for name, expected in frozen.items(): assert digest(name) == expected, name
    sources = {str(HERE/n): digest(HERE/n) for n in (
        'build_window_candidates.py', 'window_candidate_policy.py', 'test_window_candidate_policy.py', 'WINDOW_CANDIDATE_PLAN.md')}
    result = dict(blocks=blocks, inputs=inputs, frozen_sources_and_inputs=frozen, sources=sources,
        qualification='219 labeled candidate entries from accepted source fits; duplicate coordinates retained. '
        '112 first fits (three explicit96-iteration replacements) and107accepted original winners. '
        'Candidate construction never accesses reference coordinates or error fields; transferred coordinates are proposals, not audited target fits.')
    with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(blocks=len(blocks), candidates=sum(len(b['candidates']) for b in blocks))))


if __name__ == '__main__': main()
