import pytest

from reports.ALGO08.v3.ds30_repeatability import BUILDS, HOUR_NS, compare, match_neighbors


def test_matching_preserves_prefix_sites_and_unique_physical_inputs():
    ids = ["a", "b", "c", "d", "e", "f", "g"]
    centers = [[1, 2], [1, 2], [1, 2], [1, 2], None, [5, 4], [1, 2]]
    content = ["a", "a", "c", "d", "e", "f", "g"]
    times = dict(zip(ids, [0, 0, HOUR_NS, HOUR_NS + 1, 5, 5, 1], strict=True))
    assigned = {k: dict(reference=r, physical_content=d) for k, r, d in zip(ids, centers, content, strict=True)}
    assert match_neighbors(ids[:4], assigned, times) == [("a", "c", 3600)]
    assert match_neighbors(ids, assigned, times) == [("a", "c", 3600), ("b", "g", 1e-9)]


def test_report_exposes_withholds_and_uses_identical_pairs_for_both_medians():
    positions = {}
    for i, case in enumerate(("a", "b", "c", "d")):
        for role in BUILDS:
            lon = (i % 2) * (2 if role == "successor" else 1)
            point = None if (case, role) == ("c", "installed") else [0, lon]
            positions[case, role] = {"c0": {"latlon": point}}
    result = compare([("a", "b", 2), ("c", "d", 10)], positions, "c0")
    assert result["pairs"] == 2 and result["shared"] == result["candidate_more_variable"] == 1
    assert result["paired_fixes"] == {"installed": 1, "successor": 2}
    assert result["median_separation_km"]["successor"] == pytest.approx(2 * result["median_separation_km"]["installed"])
    assert compare([], {}, "c0")["median_separation_km"] == dict.fromkeys(BUILDS)
