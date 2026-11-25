"""Measure one original worker from its own PID namespace."""

import json
import resource
import subprocess
import sys
from pathlib import Path
from time import monotonic, process_time


def measure(command):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start, self_start = monotonic(), process_time()
    status = subprocess.run(command, check=False).returncode
    wall, meter_cpu = monotonic() - start, process_time() - self_start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    keys = dict(
        user_cpu_s="ru_utime",
        system_cpu_s="ru_stime",
        major_faults="ru_majflt",
        minor_faults="ru_minflt",
        input_blocks="ru_inblock",
        output_blocks="ru_oublock",
        voluntary_switches="ru_nvcsw",
        involuntary_switches="ru_nivcsw",
    )
    counters = {key: getattr(after, name) - getattr(before, name) for key, name in keys.items()}
    return dict(
        counters,
        cpu_s=counters["user_cpu_s"] + counters["system_cpu_s"],
        wall_s=wall,
        measurement_parent_cpu_s=meter_cpu,
        exit_code=status,
    )


if __name__ == "__main__":
    path, *worker = sys.argv[1:]
    if not worker:
        raise ValueError("Supply the one timed worker command")
    result = measure(worker)
    with Path(path).open("x") as output:
        json.dump(result, output, allow_nan=False, sort_keys=True)
        output.write("\n")
    raise SystemExit(result["exit_code"])
