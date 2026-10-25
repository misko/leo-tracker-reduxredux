"""Independently check the frozen recovery protocol and prepared source ownership."""
import hashlib
import json
from pathlib import Path

import numpy as np

from matched_controls import load_baseline
from probe_ds23_graph_seeded_paths import build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RECOVERY = ROOT/'recovery'


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol = read(RECOVERY/'protocol.json')
    assert read(RECOVERY/'protocol_seal.json')['protocol_sha256'] == sha(RECOVERY/'protocol.json')
    bindings = 0
    for group in ('source_sha256', 'input_sha256'):
        for name, digest in protocol[group].items():
            assert sha(name) == digest, name
            bindings += 1
    assert protocol['cases'] == ['DS24-0095', 'DS24-0087']
    assert protocol['arms'] == ['c0', 'fitted_c']
    assert protocol['receiver_model'] == 'exact_saved_baseline'
    for field in ('no_GPS', 'no_raw_IQ', 'no_receiver_candidate', 'no_native_paths', 'no_parent_ID_loss', 'no_incumbent_mode_loss'):
        assert protocol[field] is True
    assert protocol['ordinary_phase_rounds'] == protocol['constrained_phase_rounds'] == 5
    assert protocol['ordinary_position_steps'] == 48 and protocol['constrained_position_steps'] == 40
    assert protocol['constrained_minimum_slack'] == -.25 and protocol['constrained_interior'] == .01
    assert protocol['graph_seconds_per_case'] == 600 and protocol['support_seconds_per_case'] == 240
    assert protocol['global_pilot_seconds'] == 1800 and protocol['numerical_workers'] == protocol['threads'] == 1
    ranking = read('/srv/bulk/leo/research/ds24-bottlenecks-20261024/information/all_cases.json')['rows']
    ranking = sorted(ranking, key=lambda r: (-r['arms']['c0']['curved']['all']['principal_sigma_km'][0], r['case']))
    assert [row['case'] for row in ranking[:2]] == protocol['cases']
    prepared = read(RECOVERY/'prepared_seal.json')
    assert prepared['protocol_sha256'] == sha(RECOVERY/'protocol.json')
    for name, digest in prepared['files'].items():
        assert sha(RECOVERY/name) == digest, name
    members = read(HERE/'baseline_membership.json')['cases']
    rows = []
    for case in protocol['cases']:
        parent = read(RECOVERY/case/'parent.json')
        inventory = read(RECOVERY/case/'inventory.json')
        d = load_baseline(case)
        assert parent['node'] == d['node'] and parent['entries'] == d['entries']
        assert parent['model'] == d['model'] and parent['arms'] == d['arms']
        for key in ('mask', 'powers', 'means'):
            np.testing.assert_array_equal(parent[key], d['keep' if key == 'mask' else key])
        scan = d['scan']
        cutoff = scan.receipt['cutoff_utc_ns']
        for element in scan.elements.values():
            provenance = element['provenance']
            assert provenance['element_epoch_utc_ns'] <= cutoff and provenance['collected_utc_ns'] <= cutoff
        old = members[case]
        curved = set().union(*(set(r['curved_ids']) for r in old['family_membership']))
        predictive = set().union(*(set(r['predictive_ids']) for r in old['family_membership']))
        observations = read(Path('/srv/bulk/leo/research/ds25-20261024')/case/'observations.json')
        observation_ids = {r['observation_id'] for r in observations}
        assert len(observation_ids) == len(observations)
        for arm, coverage in parent['coverage'].items():
            assert set(coverage['curved_observation_ids']) == curved
            assert set(coverage['predictive_observation_ids']) == predictive
            assert set(coverage['accepted_observation_ids']) <= observation_ids
            assert curved|predictive <= set(coverage['accepted_observation_ids'])
            assert coverage['total_GLRT'] == len(observations)
            assert coverage['associated'] == len(coverage['accepted_observation_ids'])
        occupied = set().union(*(set(r['accepted_observation_ids']) for r in parent['coverage'].values()))
        p = build(d, 'default', 'c0', d['arms']['c0']['phase_reference'])
        expected = []
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            track = scan.tracks[i]
            ids = set(track['observation_ids'])
            if d['keep'][sl].any() or ids & occupied:
                continue
            if i in scan.curved and len(ids) >= 12:
                expected.append(dict(component=track['key'], points=len(ids), span_s=float(np.ptp(track['times'])),
                    observation_ids=track['observation_ids'], row_index=p.rows.index(row)))
        expected.sort(key=lambda r: (-r['span_s'], -r['points'], r['component']))
        assert [r['component'] for r in expected[:3]] == [r['component'] for r in inventory['candidate_targets']]
        for actual, candidate in zip(inventory['candidate_targets'], expected[:3], strict=True):
            assert actual['observation_ids'] == candidate['observation_ids']
            assert not set(actual['observation_ids']) & occupied
        rows.append(dict(case=case, whole_source_targets=len(expected[:3]),
            parent_curved_points=len(curved), parent_predictive_points=len(predictive),
            parent_associated={a:c['associated'] for a,c in parent['coverage'].items()},
            all_GLRT_points=len(observations), causal_candidate_elements=len(scan.elements)))
    tests = HERE/'recovery_component_tests.txt'
    assert tests.exists() and '8 passed' in tests.read_text()
    output = dict(all_passed=True, GPS_used=False, no_position_fits=True,
        protocol_sha256=sha(RECOVERY/'protocol.json'), prepared_seal_sha256=sha(RECOVERY/'prepared_seal.json'),
        source_sha256=sha(Path(__file__)), component_test_log_sha256=sha(tests), verified_file_bindings=bindings,
        rows=rows, source_review='Original whole-source nomination/configuration and near-feasible rescue semantics retained; parent accepted/likelihood IDs and original physical mode support protected; support control separately selected; no new RX1 or native-path intervention',
        coordinator_go_still_required=True)
    with (HERE/'recovery_preflight.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__': main()
