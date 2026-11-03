import pytest
from probe_algo03_discovery_rescue import nomination_wins,ranked_finalists


def test_lower_rf_loss_must_pay_search_cost_on_identical_observations():
    assert nomination_wins(100.,90.,1000,1000,13)
    assert not nomination_wins(100.,99.,1000,1000,13)
    assert not nomination_wins(100.,float("nan"),1000,1000,13)


def test_nomination_cannot_win_by_deleting_observations():
    with pytest.raises(ValueError,match="same nonempty"):
        nomination_wins(100.,0.,1000,999,13)


def test_duplicate_nomination_losses_use_start_index_not_directory_order():
    rows=[dict(start_index=k,arms={"c0":{"negative_twice_elbo":20.}}) for k in (9,1,0)]
    assert [r["start_index"] for r in ranked_finalists(rows)]==[0,1]
    rows[0]["arms"]["c0"]["negative_twice_elbo"]=19.
    assert [r["start_index"] for r in ranked_finalists(rows)]==[9,0]
