import pytest

from reports.ALGO08.v3.integrated_stage_budget import rows


def test_disjoint_clocks_reconstruct_both_complete_pairs():
    measured = rows()
    assert [row["order"] for row in measured] == ["positive_first", "withholding_first"]
    for row in measured:
        assert sum(row[key] for key in ("acquisition", "solve", "render", "other", "withheld")) == pytest.approx(row["total"])
        assert row["baseline"] == pytest.approx(12.241695752)
        assert 2.8 < row["acquisition"] < 3.0 and 2.0 < row["solve"] < 2.2
    assert measured[0]["total"] < measured[0]["baseline"] / 1.6 < measured[1]["total"]
