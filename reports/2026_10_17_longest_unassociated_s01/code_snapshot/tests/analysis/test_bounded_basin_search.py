import numpy as np

from leo.analysis.research.bounded_basin_search import bounded_basin_search


def test_search_covers_disk_and_allocates_all_three_basins_without_duplicate_calls():
    calls = []
    target = np.array([-40.0, 35.0])

    def score(point):
        calls.append(tuple(np.round(point, 9)))
        return float(np.sum((point - target) ** 2))

    result = bounded_basin_search(score)
    assert result["basins"] == 3
    assert len(result["endpoints"]) == 3
    assert result["evaluations"] == len(set(calls)) == len(calls)
    assert result["evaluations"] <= result["maximum_evaluations"] == 133
    assert all(np.linalg.norm(point) <= 250 + 1e-8 for point in calls)
    assert min(np.linalg.norm(r["east_north_km"] - target) for r in result["endpoints"]) < 0.25
    assert all(len(result["scales_km"]) == 10 for _ in result["endpoints"])
