"""Use the existing early screen with deployed conservative trim and final selection."""

from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def screened_stock_recovery():
    """Activate before constructing the frozen saved-input solver composition."""
    from leo.analysis.localization_v3 import conservative_recovery
    from tools.pipeline_eval.variants import algo08_collapsed_repair, v5_core, v5_screen_winner

    # Capture the deployed trim before the composition installs its tiled variant.
    original_salvage = conservative_recovery.salvage
    metrics = {}

    def nominate(scan):
        return v5_screen_winner.screen_nodes(scan, v5_core.ranked_initial_nodes(scan)[:3], metrics)

    @contextmanager
    def select_stock_finish():
        with (patch.object(v5_core, "initial_selection", nominate),
              patch.object(conservative_recovery, "salvage", original_salvage)):
            yield

    # Keep the ordinary v5 inference entry point and all its recovery gates.
    with patch.object(algo08_collapsed_repair, "binding", select_stock_finish):
        yield metrics
