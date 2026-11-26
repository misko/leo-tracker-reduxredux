"""ALGO07 API projection through validated public completed-result ports."""

from leo.contracts.fast_graph_position_v5 import MODEL_VERSION as PREVIOUS_VERSION
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION
from leo.contracts.fast_standard_analysis import COMPACT_MODELS, standard_label, standard_model
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.graph_position_view_v6 import completed_view
from leo.storage.fast_scan import safe_id
from leo.storage.graph_position_lookup_v5 import (
    graph_position_view as previous_view,
)


class GraphPositionLookupV6:
    def __init__(self, root, model_version, *, lookup=None, previous=None):
        if model_version != MODEL_VERSION:
            raise ValueError("Explicit ALGO07 model required")
        self.lookup = lookup if lookup is not None else FastGraphPositionStoreV6(root)
        self.previous = (
            previous if previous is not None else previous_view(root, PREVIOUS_VERSION)
        )

    def detail(self, run_id):
        safe_id(run_id)
        model = standard_model(run_id)
        if model in COMPACT_MODELS:
            return dict(
                run_id=run_id,
                selected_model=MODEL_VERSION,
                state="unavailable",
                baseline=None,
                selected=None,
                position=None,
                fallback=False,
                reason=f"{standard_label(model)} publishes its position in standard analysis.",
            )
        terminal = self.lookup.completed_run(run_id)
        if terminal is not None:
            return completed_view(run_id, terminal)
        view = self.previous.detail(run_id)
        view.update(
            selected_model=MODEL_VERSION,
            fallback=True,
            reason="Awaiting qualified ALGO07 result; "
            + (view.get("reason") or "ALGO06 retained"),
        )
        return view


def graph_position_view(root, model_version):
    if model_version == MODEL_VERSION:
        return GraphPositionLookupV6(root, model_version)
    return previous_view(root, model_version)
