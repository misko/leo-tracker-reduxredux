"""Load only producer-runtime dependencies in the authenticated archive worker."""

import sys
from collections import Counter
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from . import raw_stream_reader, recording_to_v5

METRIC_PREFIX = "bounded compressed IQ "


def proc_read_bytes():
    for line in Path("/proc/self/io").read_text().splitlines():
        if line.startswith("read_bytes:"):
            return int(line.split()[1])
    raise ValueError("process storage-read counter is unavailable")


def raw_worker():
    from leo.storage.short_window import ShortWindowReader

    started, cpu, physical = perf_counter(), process_time(), proc_read_bytes()
    stats = Counter()

    def windows(reader, **kwargs):
        return raw_stream_reader.streamed_windows(reader, stats, **kwargs)

    with patch.object(ShortWindowReader, "windows", windows):
        recording_to_v5.main()
    print(
        METRIC_PREFIX
        + recording_to_v5.encoded(
            dict(
                stats,
                storage_read_bytes=proc_read_bytes() - physical,
                worker_wall_s=perf_counter() - started,
                worker_cpu_s=process_time() - cpu,
                peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            )
        ),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    raw_worker()
