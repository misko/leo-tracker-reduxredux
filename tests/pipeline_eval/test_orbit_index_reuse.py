import pytest

from reports.ALGO08.v3.orbit_index_reuse import contents, replay


def test_source_reuse_preserves_cutoff_and_deduplicates_repeated_bodies():
    key = "b3" * 32
    snapshots = {f"{stamp}-{key}.tle": key for stamp in (13, 17)}
    assert contents(snapshots, 17) == (key,)
    with pytest.raises(ValueError):
        contents(snapshots, 16)


def test_reuse_model_charges_first_builds_and_real_capacity_evictions():
    scans = [(2, "b", ("two", "three")), (1, "a", ("one", "two")), (3, "c", ("one",))]
    assert [r["hits"] for r in replay(scans, 2)["rows"]] == [0, 1, 0]
    assert replay(scans, 3)["hits"] == 2


def test_per_scan_retention_does_not_evict_a_hit_before_declared_use():
    scans = [(1, "first", ("a", "b", "c")), (2, "repeat", ("a", "b", "c"))]
    assert replay(scans, 2)["hits"] == 0
    assert replay(scans, 2, change_at_scan_end=True)["hits"] == 2
