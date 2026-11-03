"""Shared validation for bounded streaming analyzers."""

from __future__ import annotations

from collections.abc import Iterator

from leo.domain.iq import IqBlock
from leo.pipeline.contracts import IqReader


class IqStreamError(ValueError):
    """The reader returned geometry inconsistent with its declaration."""


def validated_blocks(reader: IqReader, *, block_samples: int) -> Iterator[IqBlock]:
    if block_samples <= 0:
        raise ValueError("block_samples must be positive")
    if reader.sample_count < 0:
        raise IqStreamError("reader sample_count must be non-negative")
    if reader.sample_rate_hz <= 0:
        raise IqStreamError("reader sample_rate_hz must be positive")
    if not reader.receiver_ids or tuple(sorted(set(reader.receiver_ids))) != reader.receiver_ids:
        raise IqStreamError("reader receiver IDs must be non-empty, unique, and sorted")

    previous_end = 0
    for block in reader.iter_blocks(block_samples=block_samples):
        if not isinstance(block, IqBlock):
            raise IqStreamError("reader yielded a value that is not an IqBlock")
        if block.metadata.receiver_ids != reader.receiver_ids:
            raise IqStreamError("block receiver IDs do not match reader receiver IDs")
        if block.metadata.sample_count > block_samples:
            raise IqStreamError("reader yielded a block larger than requested")
        start = block.metadata.session_sample_start
        end = start + block.metadata.sample_count
        if start < previous_end:
            raise IqStreamError("IQ blocks overlap or are out of order")
        if end > reader.sample_count:
            raise IqStreamError("IQ block extends beyond declared sample_count")
        previous_end = end
        yield block
