from unittest.mock import patch

from leo.analysis.localization_v3 import conservative_recovery
from tools.pipeline_eval.variants import algo08_collapsed_repair, v5_core, v5_screen_winner
from tools.pipeline_eval.variants.algo08_screened_stock_recovery import screened_stock_recovery


def test_deployed_trim_and_stock_infer_with_existing_ranked_nomination(monkeypatch):
    stock_trim = conservative_recovery.salvage
    stock_infer, stock_selection = v5_core.infer, v5_core.initial_selection
    collapsed_binding = algo08_collapsed_repair.binding
    tiled = object()
    scan, decisions = object(), object()
    options = [object() for _ in range(4)]

    def rank(value):
        assert value is scan
        return options

    def screen(value, ranked, metrics):
        assert value is scan and ranked == options[:3]
        metrics["winning_rank"] = 2
        return decisions

    monkeypatch.setattr(v5_core, "ranked_initial_nodes", rank)
    monkeypatch.setattr(v5_screen_winner, "screen_nodes", screen)
    with (screened_stock_recovery() as receipt,
          patch.object(conservative_recovery, "salvage", tiled)):
        with algo08_collapsed_repair.binding():
            assert conservative_recovery.salvage is stock_trim
            assert v5_core.infer is stock_infer
            assert v5_core.initial_selection(scan) is decisions
        assert conservative_recovery.salvage is tiled
        assert v5_core.initial_selection is stock_selection
    assert conservative_recovery.salvage is stock_trim
    assert algo08_collapsed_repair.binding is collapsed_binding
    assert receipt == {"winning_rank": 2}
