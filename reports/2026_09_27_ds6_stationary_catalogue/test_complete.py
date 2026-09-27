"""Completion gate for the frozen catalogue experiment."""
import json
import numpy as np
from audit import HERE, REPORTS, digest


def test_frozen_inputs_and_all_selected_tracks():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    assert len(set(protocol['sessions'])) == 3
    assert protocol['source_sha256'] == digest(HERE / 'audit.py')
    for name, value in protocol['files'].items():
        assert digest(REPORTS / name) == value
    for session in protocol['sessions']:
        result = json.loads((HERE / f'{session}.json').read_text())
        baseline = json.loads((REPORTS / '2026_09_27_ds6_element_freshness' / f'{session}.json').read_text())
        assert result['complete']
        assert result['protocol_sha256'] == digest(HERE / 'protocol.json')
        rows = result['tracks']
        assert len(rows) == len(baseline['shortlists'])
        assert {r['track_id'] for r in rows} == set(baseline['shortlists'])
        for r in rows:
            assert r['visible_candidates'] > 0
            assert 0 < r['retained_mass'] <= 1 + 1e-10
            assert np.isfinite(r['full_held_change'])
            np.testing.assert_allclose(r['full_train_gain'], -np.log(r['retained_mass']), atol=1e-9)
        assert result['training_best_missing_count'] == sum(r['training_best_missing'] for r in rows)
        np.testing.assert_allclose(result['total_full_train_gain'], sum(r['full_train_gain'] for r in rows))
        np.testing.assert_allclose(result['total_full_held_change'], sum(r['full_held_change'] for r in rows))
