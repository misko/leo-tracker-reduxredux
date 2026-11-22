"""Scope the two-refresh nomination to the original compact solver finish."""

from contextlib import contextmanager
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_core, v5_screen_winner


@contextmanager
def screened_nomination():
    details = {}

    def select(scan):
        ranked = v5_core.ranked_initial_nodes(scan)[:3]
        return v5_screen_winner.screen_nodes(scan, ranked, details)

    with patch.object(v5_core, "initial_selection", select):
        yield details
