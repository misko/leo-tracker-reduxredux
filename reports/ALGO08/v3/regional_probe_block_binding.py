"""Use guarded native blocks at the original bilateral proof boundary."""

from contextlib import contextmanager
from unittest.mock import patch

from dense_geographic_projection import checked_runtime
from regional_probe_block import OrderedProbeScores, ProbeBlock
from regional_track_scores import TrackScores
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal


@contextmanager
def guarded_projection(single, stock, block, original_projection):
    """Retain the prepared scalar path if a request cannot use the block."""
    kernel, _ = checked_runtime()

    def evaluate(prepared, catalogue, region):
        points, original, meta = kernel._prepare_probe_scores(prepared, catalogue, region)
        scalar = original
        packed = native = ordered = None
        try:
            packed = TrackScores(stock, original)
            scalar = packed
            native = ProbeBlock(block, packed)
            ordered = OrderedProbeScores(
                points, region.width_km, native, scalar, guaranteed_only=True
            )
        except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
            counts["block_setup_fallbacks"] += 1

        def receiver_scores(point):
            result = ordered(point) if ordered is not None else scalar(dict(point))
            return result["receiver_scores"]

        decision = evaluate_terminal(points, region.width_km, receiver_scores)
        counts["consumed"] += decision["probes_evaluated"]
        if native is not None:
            counts["block_positions"] += native.computed
            counts["block_calls"] += native.calls
        if packed is not None:
            counts["scalar_positions"] += packed.native
            counts["fallbacks"] += packed.fallbacks
        if ordered is not None:
            counts["fallbacks"] += int(ordered.failed)
        return dict(decision, **meta)

    with (original_projection(single) as counts,
          patch.object(kernel, "evaluate_veto", evaluate)):
        yield counts
