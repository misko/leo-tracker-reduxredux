from leo.analysis.localization_v3.reassociation_history import select_history
from leo.operations.localization_v3_history import collect_versions
from tests.operations.test_localization_v3_inputs import fixture


def test_archive_order_and_causal_boundaries(monkeypatch):
    hour = 3600 * 10**9
    cutoff, reader, reads = fixture(
        monkeypatch,
        [
            (-hour, 232),
            (-2 * hour, 232),
            (-72 * hour, 230),
            (-72 * hour - 1, 229),
            (1, 231),
            (-hour, 234),
        ],
    )
    result = collect_versions(reader, cutoff)
    assert result["snapshot_count"] == 4 and len(reads) == 4
    rows = result["versions"]["44714"]
    assert len(rows) == 2 and rows[0]["collected_utc_ns"] == cutoff - hour
    assert rows[1]["collected_utc_ns"] == cutoff - 72 * hour
    picked = select_history(result, dict(cutoff=cutoff, latest={"44714": cutoff}))
    assert picked["chosen"]["44714"] == rows[0]


def test_empty_causal_archive(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(1, 232)])
    assert collect_versions(reader, cutoff)["versions"] == {} and not reads
