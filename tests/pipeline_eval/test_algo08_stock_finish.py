import pytest

from tools.pipeline_eval.variants import algo08_stock_finish, v5_core, v5_screen_winner


def test_scope_uses_top_three_exactly_once_and_restores_stock_selector(monkeypatch):
    original = v5_core.initial_selection
    scan = object()
    nodes = [object() for _ in range(4)]
    result = {"chosen": nodes[0]}

    def rank(current):
        assert current is scan
        return nodes

    def screen(current, ranked, metrics):
        assert current is scan and ranked == nodes[:3]
        metrics["initial_phase_fits"] = 9
        return result, len(ranked)

    monkeypatch.setattr(v5_core, "ranked_initial_nodes", rank)
    monkeypatch.setattr(v5_screen_winner, "screen_nodes", screen)
    with pytest.raises(ValueError, match="after screening"):
        with algo08_stock_finish.screened_nomination() as detail:
            assert v5_core.initial_selection(scan) == (result, 3)
            assert detail == {"initial_phase_fits": 9}
            raise ValueError("after screening")
    assert v5_core.initial_selection is original
