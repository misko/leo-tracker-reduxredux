"""Compare resident-memory cost on the largest sealed compressed member only."""

import json
import sys
from collections import Counter
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

from . import raw_stream_reader
from .raw_stream_archive_worker import proc_read_bytes


def measure(entries, mode):
    from leo.storage.short_window import ShortWindowReader

    if mode not in ("stock", "bounded"):
        raise ValueError("the probe compares exactly two reader paths")
    candidates = []
    for member in entries:
        reader = ShortWindowReader(Path(member["path"]).parent)
        if reader.manifest_sha256 != "sha256:" + member["sha256"]:
            raise ValueError("chunk selection requires the sealed manifest")
        candidates.extend((reader, chunk) for chunk in reader.manifest.chunks)
    reader, winner = max(candidates, key=lambda item: item[1].compressed_bytes)
    scope = dict(
        start_sequence=winner.first_sequence,
        stop_sequence=winner.first_sequence + winner.window_count,
    )
    stats = Counter()
    wall, cpu, physical = perf_counter(), process_time(), proc_read_bytes()
    windows = (
        reader.windows(**scope)
        if mode == "stock"
        else raw_stream_reader.streamed_windows(reader, stats, **scope)
    )
    windows_seen = [(w.index.sequence, w.index.iq_sha256, w.samples.nbytes) for w in windows]
    return dict(
        reader=mode,
        wall_s=perf_counter() - wall,
        cpu_s=process_time() - cpu,
        storage_read_bytes=proc_read_bytes() - physical,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        manifest_sha256=reader.manifest_sha256,
        chunk=winner.model_dump(mode="json"),
        windows_seen=windows_seen,
        read_receipt=dict(stats),
    )


if __name__ == "__main__":
    json.dump(measure(json.load(sys.stdin), sys.argv[1]), sys.stdout, allow_nan=False)
