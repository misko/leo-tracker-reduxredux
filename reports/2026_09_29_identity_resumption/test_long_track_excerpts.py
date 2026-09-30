from types import SimpleNamespace

from long_track_excerpts import temporal_choices


def test_choices_use_elapsed_time_and_margin_not_equal_observation_counts():
    points = [SimpleNamespace(support_center_utc_ns=t, margin=m, visit_index=i, candidate_rank=0)
              for i, (t, m) in enumerate([(0, 1), (1, 2), (2, 8), (50, 3), (100, 4)])]
    assert [p.visit_index for p in temporal_choices(points)] == [2, 3, 4]
