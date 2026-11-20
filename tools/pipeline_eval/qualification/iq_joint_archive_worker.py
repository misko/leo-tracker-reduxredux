"""Set a finite heap before loading the installed archive producer and GLRT."""

import json
import sys
from threading import Event, Thread
from time import monotonic_ns

from .iq_joint_resources import MEMORY_PREFIX, RAW_AS_MIB, SAMPLE_PREFIX, cap_address_space, memory


def main():
    cap_address_space(RAW_AS_MIB)
    from .raw_stream_archive_worker import raw_worker

    done = Event()
    samples = []

    def sample():
        while not done.wait(0.25):
            samples.append((monotonic_ns(), memory()["VmRSS"]))

    thread = Thread(target=sample, name="process-memory", daemon=True)
    thread.start()
    try:
        raw_worker()
    finally:
        done.set()
        thread.join()
    for stamp, rss in samples:
        print(SAMPLE_PREFIX + f"{stamp} {rss}", file=sys.stderr)
    print(MEMORY_PREFIX + json.dumps(memory(), sort_keys=True), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
