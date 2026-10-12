import pytest

from leo.analysis.continuous_merge_groups import continuous_mark_groups


def test_quota_admits_an_original_without_inventing_a_join():
    inventory = {"a": (0, 1), "b": (2, 3), "outside-quota": (4, 5)}
    groups, audit = continuous_mark_groups(
        [(0, 1), (2, 3)], [(0, 1, 2, 3), (4, 5)], inventory, [("a", "b")]
    )
    assert groups == {"joined": [(0, 1, 2, 3)], "parents": [(0, 1), (2, 3)]}
    assert audit["newly_selected_originals"] == [(4, 5)]
    assert audit["actual_selected_joined_components"] == 1


def test_shared_boundaries_remain_independent_and_both_groupings_cover_the_same_rows():
    inventory = {"a": (0, 1, 2), "b": (2, 3, 4), "c": (5, 6)}
    groups, audit = continuous_mark_groups(
        [(0, 1, 2), (2, 3, 4), (5, 6)], [(0, 1, 2, 3, 4), (5, 6)], inventory, [("a", "b")]
    )
    assert groups == {"joined": [(0, 1, 3, 4)], "parents": [(0, 1), (3, 4)]}
    assert audit["excluded_ambiguous_rows"] == [2]


def test_no_selected_joins_has_empty_groups_even_when_original_quota_changes():
    groups, audit = continuous_mark_groups([(0, 1)], [(2, 3)], {"a": (0, 1), "b": (2, 3)}, [])
    assert groups == {"joined": [], "parents": []}
    assert audit["newly_selected_originals"] == [(2, 3)]


@pytest.mark.parametrize("components", [[("a", "missing")], [("a", "b"), ("b", "a")]])
def test_unknown_and_ambiguous_join_authority_is_rejected(components):
    with pytest.raises(ValueError):
        continuous_mark_groups([(0, 1)], [(0, 1, 2, 3)], {"a": (0, 1), "b": (2, 3)}, components)
