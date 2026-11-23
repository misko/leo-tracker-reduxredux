"""Apply the reviewed association gather only in the shared full-catalogue rank."""

from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from cold_track_row_reuse import shared_association_rows


def rank_with_centre_rows(original, discovery, counts):
    def rank(scan):
        projection = discovery.phase_linear_frequency
        tables = getattr(projection, "__self__", None)
        if (tables is None or getattr(projection, "__qualname__", None) != "AnchorTables.projection"
                or tables.scan is not scan
                or Path(projection.__code__.co_filename).name != "algo08_blind_rank.py"):
            counts["ordinary_ranks"] += 1
            return original(scan)
        counts["shared_ranks"] += 1
        with shared_association_rows(scan, tables, counts):
            return original(scan)

    return rank


@contextmanager
def cold_track_rows():
    from leo.analysis.localization_v3 import discovery
    from tools.pipeline_eval.variants import v5_core

    counts = Counter(shared_ranks=0, ordinary_ranks=0)
    with patch.object(v5_core, "ranked_initial_nodes", rank_with_centre_rows(v5_core.ranked_initial_nodes, discovery, counts)):
        yield counts
