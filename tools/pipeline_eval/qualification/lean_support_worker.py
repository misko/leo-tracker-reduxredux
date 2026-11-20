"""Run a lean track receiver inside the sealed numerical sandbox."""

import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time


def main():
    started = process_time()
    from tools.pipeline_eval.variants import robust_em, robust_orbit_fit, robust_support

    receiver = {m.METHOD: m for m in (robust_em, robust_orbit_fit, robust_support)}[sys.argv[1]]
    packet = json.load(sys.stdin)
    result = receiver.infer(packet["observation"], packet["offer"], packet["catalogue"])
    json.dump(
        dict(
            result=result,
            worker_cpu_s=process_time() - started,
            max_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        ),
        sys.stdout,
        allow_nan=False,
    )


if __name__ == "__main__":
    main()
