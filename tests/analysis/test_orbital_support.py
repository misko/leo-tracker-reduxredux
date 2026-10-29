from types import SimpleNamespace

import numpy as np

from leo.analysis.research.orbital_support import restrict_to_active_orbital_support


def model(mask):
    tracks = [dict(receiver=1, channel=1), dict(receiver=1, channel=3),
              dict(receiver=1, channel=1), dict(receiver=2, channel=8),
              dict(receiver=1, channel=8)]
    return SimpleNamespace(
        rows=[dict(candidate_index=j) for j in (10, 10, 10, 20, 20)],
        members=list(range(5)), slices=[slice(2*i, 2*i+2) for i in range(5)],
        keep=np.asarray(mask, bool), scan=SimpleNamespace(tracks=tracks),
        labels=[10, 20], supported=[10, 20], supported_local=[0, 1],
        reference=np.array([.5, -.2]), alias=[0, 0, 1, -1, 0],
        mode_bank=object(),
    )


def test_failed_second_owner_reduces_complexity_without_dropping_good_data():
    p = model([1, 1, 0, 0, 1, 1, 1, 1, 1, 1])
    before = (p.keep.copy(), p.reference.copy(), p.alias.copy(), p.mode_bank)
    assert restrict_to_active_orbital_support(p) is p
    assert p.supported == [20] and p.supported_local == [1]
    assert p.orbital_support_backoff["disabled_families"] == [10]
    assert p.orbital_support_backoff["active_owners"][10] == [(1, 1)]
    np.testing.assert_array_equal(p.keep, before[0])
    np.testing.assert_array_equal(p.reference, before[1])
    assert p.alias == before[2] and p.mode_bank is before[3]


def test_two_distinct_channels_keep_orbit_modes_and_empty_rows_do_not_vote():
    p = model([1]*6 + [0]*4)
    restrict_to_active_orbital_support(p)
    assert p.supported == [10] and p.supported_local == [0]
    assert p.orbital_support_backoff["disabled_families"] == [20]


def test_all_supported_evidence_preserves_existing_model_coordinates():
    p = model([1]*10)
    restrict_to_active_orbital_support(p)
    assert p.supported == [10, 20] and p.supported_local == [0, 1]
    assert not p.orbital_support_backoff["disabled_families"]
