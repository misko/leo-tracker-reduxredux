from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_shared_probe_position import peak_role, refine_original
from leo.analysis.research.retained_track_likelihood import PERIOD


def fixture():
    jobs = [dict(first=dict(cfo_hz=100., probe_observation_id='a'), second=dict(cfo_hz=10000.))]
    rows = [dict(first_fit=dict(CFO_hz=108.), second_fit=dict(CFO_hz=9997.))]
    return jobs, rows


def test_RF_refinement_preserves_alias_and_never_substitutes_other_component():
    jobs, rows = fixture()
    scan = SimpleNamespace(tracks=[dict(values=np.array([100.+PERIOD, 50000.]), observation_ids=['a', 'b'])])
    updated, changes = refine_original(scan, jobs, rows)
    np.testing.assert_allclose(updated.tracks[0]['values'], [108.+PERIOD, 50000.])
    np.testing.assert_allclose(scan.tracks[0]['values'], [100.+PERIOD, 50000.])
    assert changes == {'a': {'role': 'first', 'CFO_delta_hz': 8.}}


def test_unrelated_original_winner_on_same_probe_is_not_reassigned():
    jobs, rows = fixture()
    scan = SimpleNamespace(tracks=[dict(values=np.array([50000.]), observation_ids=['a'])])
    updated, changes = refine_original(scan, jobs, rows)
    assert not changes
    np.testing.assert_array_equal(updated.tracks[0]['values'], [50000.])


def test_RF_component_matching_uses_physical_alias_and_rejects_ambiguous_peaks():
    jobs, _ = fixture()
    assert peak_role(10000.-2*PERIOD, jobs[0]) == 'second'
    close = dict(first=dict(cfo_hz=100.), second=dict(cfo_hz=200.))
    assert peak_role(150., close) is None
