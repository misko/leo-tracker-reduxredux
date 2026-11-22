"""Advise one bounded compressed payload ahead of a serial verified receiver."""

import os
import stat
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.storage.fast_scan import FastSegmentSource
from leo.storage.pinned import PinnedLocalRoot


PREFIX_BYTES = 16 * 1024**2


@dataclass
class MemberHints:
    attempts: int = 0
    submitted: int = 0
    submitted_bytes: int = 0
    cpu_ns: int = 0
    wall_ns: int = 0


def advise_prefix(root, chunk, advise, willneed):
    """Open a manifest-listed regular file for advisory I/O only."""
    member = PurePosixPath(chunk.payload_relative_path)
    try:
        with ExitStack() as stack:
            directory = stack.enter_context(closing(PinnedLocalRoot(root)))
            if member.parent.parts:
                directory = stack.enter_context(closing(directory.child(*member.parent.parts)))
            fd = os.open(member.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory.fileno())
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_size != chunk.compressed_bytes or info.st_size <= 0):
                return 0
            length = min(info.st_size, PREFIX_BYTES)
            advise(fd, 0, length, willneed)
            return length
    except (OSError, ValueError):
        # Leave path, seal and I/O errors to the real reader when it reaches the member.
        return 0


def hinted_windows(windows, source, following, stats, advise, willneed):
    with closing(windows):
        for window in windows:
            next_chunk = following.get(window.sequence)
            if next_chunk is not None:
                cpu, wall = process_time_ns(), perf_counter_ns()
                stats.attempts += 1
                submitted = advise_prefix(source.reader.path, next_chunk, advise, willneed)
                stats.submitted += bool(submitted)
                stats.submitted_bytes += submitted
                stats.cpu_ns += process_time_ns() - cpu
                stats.wall_ns += perf_counter_ns() - wall
            yield window


def following_members(source):
    start, stop = source.start_sequence, source.stop_sequence
    chunks = [chunk for chunk in source.reader.manifest.chunks
              if chunk.first_sequence + chunk.window_count > start and chunk.first_sequence < stop]
    return {max(start, chunk.first_sequence): next_chunk
            for chunk, next_chunk in zip(chunks, chunks[1:])}


@contextmanager
def compressed_member_lookahead():
    """Hint only the next in-scope member within each sealed segment."""
    stats = MemberHints()
    advise, willneed = getattr(os, "posix_fadvise", None), getattr(os, "POSIX_FADV_WILLNEED", None)
    if advise is None or willneed is None:
        yield stats
        return
    original = FastSegmentSource.windows

    def windows(source):
        following = following_members(source)
        released = original(source)
        if not following:
            return released
        return hinted_windows(released, source, following, stats, advise, willneed)

    with patch.object(FastSegmentSource, "windows", windows):
        yield stats
