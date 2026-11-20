"""Inference worker. The sandbox supplies only numerical observations and orbits."""

import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time


def main():
    start = process_time()
    from tools.pipeline_eval.variants.robust_em import infer

    packet = json.load(sys.stdin)
    result = infer(packet["observation"], packet["offer"], packet["catalogue"])
    receipt = dict(
        result=result,
        worker_cpu_s=process_time() - start,
        max_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )
    json.dump(receipt, sys.stdout, allow_nan=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
