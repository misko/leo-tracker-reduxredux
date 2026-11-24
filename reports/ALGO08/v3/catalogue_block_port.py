"""Opt in to the tested grouped scorer at the existing cold-row reuse port."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from catalogue_block_rank import install


@contextmanager
def use_catalogue_blocks():
    """Enable blocks around one serialized research publication and yield counters."""
    import cold_track_row_entry as entry

    original = entry.shared_association_rows
    counts = Counter(admitted_ranks=0, original_ranks=0)

    @contextmanager
    def selected(scan, tables, original_counts, *, borrow=False):
        with ExitStack() as scopes:
            try:
                scopes.enter_context(install(scan, tables, counts, borrow=borrow))
            except (AttributeError, ValueError):
                scopes.enter_context(original(scan, tables, original_counts, borrow=borrow))
                counts["original_ranks"] += 1
            else:
                counts["admitted_ranks"] += 1
            yield

    with patch.object(entry, "shared_association_rows", selected):
        yield counts
