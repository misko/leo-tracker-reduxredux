import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('replication16_prepare_test', Path(__file__).with_name('prepare.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_training_selection_preserves_cross_receiver_visits():
    tracks = [dict(track_id=t, training_mask=[True, False], visits=[7, 8],
                   times_s=[1., 2.], measured_hz=[100., 200.]) for t in ('a', 'b')]
    rows = prepare.select_training_rows(tracks, ('b', 'a'))
    assert [r['track_id'] for r in rows] == ['b', 'a']
    assert [r['visit'] for r in rows] == [7, 7]
    assert all(r['observation_index'] == 0 for r in rows)
    with pytest.raises(ValueError):
        prepare.select_training_rows(tracks, ('missing',))


def test_duplicate_identity_distinguishes_receivers():
    rows = [dict(ordinal=0, visit=7, receiver_id=0), dict(ordinal=1, visit=7, receiver_id=1)]
    assert prepare.duplicate_groups(rows, ('visit',)) == [dict(identity=[7], ordinals=[0, 1])]
    assert prepare.duplicate_groups(rows, ('visit', 'receiver_id')) == []
    rows[1]['receiver_id'] = 0
    assert prepare.duplicate_groups(rows, ('visit', 'receiver_id')) == [dict(identity=[7, 0], ordinals=[0, 1])]
