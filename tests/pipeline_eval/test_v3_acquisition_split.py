import pytest

from reports.ALGO08.v3.acquisition_split import summarize


def test_counts_both_antennas_and_only_observed_callback_time():
    probes = [dict(visit_index=i, receiver_id=rx, candidates=list(range(n)))
              for i, rx, n in [(0, 0, 1), (0, 1, 1), (3, 0, 0), (3, 1, 2)]]
    rows = [(0, 200_000_000, 400_000_000), (3, 900_000_000, 1_000_000_000)]
    assert summarize(rows, probes, {3}) == {
        "anchors": dict(visits=1, selections=2, cpu_s=.9, wall_s=1.),
        "nonanchors": dict(visits=1, selections=2, cpu_s=.2, wall_s=.4),
    }
    with pytest.raises(ValueError, match="opportunities"):
        summarize(rows[::-1], probes, {3})
