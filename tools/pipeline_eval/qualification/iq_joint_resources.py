"""Process-local memory telemetry and simultaneous raw-lane samples."""

import json
from pathlib import Path
from resource import RLIMIT_AS, getrlimit, setrlimit

RAW_AS_MIB = 768
ASSEMBLY_AS_MIB = 768
SAMPLE_PREFIX = "iq-to-joint rss "
MEMORY_PREFIX = "iq-to-joint process "
MAX_SAMPLE_SEPARATION_NS = 550_000_000


def cap_address_space(mib):
    bound = mib * 1024**2
    setrlimit(RLIMIT_AS, (bound, bound))


def memory():
    fields = {"VmHWM", "VmPeak", "VmRSS", "VmSize"}
    values = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in fields:
            values[key] = int(value.split()[0])
    if set(values) != fields:
        raise ValueError("process memory counters are unavailable")
    return dict(values, address_space_limit_mib=getrlimit(RLIMIT_AS)[0] // 1024**2)


def raw_memory(paths):
    samples, terminal = [], []
    for lane, path in enumerate(paths):
        reports = []
        for line in path.read_text().splitlines():
            if line.startswith(MEMORY_PREFIX):
                reports.append(json.loads(line.removeprefix(MEMORY_PREFIX)))
            elif line.startswith(SAMPLE_PREFIX):
                when, rss = map(int, line.removeprefix(SAMPLE_PREFIX).split())
                samples.append((when, lane, rss))
        if len(reports) != 1 or reports[0]["address_space_limit_mib"] != RAW_AS_MIB:
            raise ValueError("completed detector lane lacks a finite memory receipt")
        terminal.append(reports[0])
    last, combined, pairs = [None] * len(terminal), 0, 0
    for when, lane, rss in sorted(samples):
        last[lane] = when, rss
        if all(value is not None and when - value[0] <= MAX_SAMPLE_SEPARATION_NS for value in last):
            combined = max(combined, sum(value[1] for value in last))
            pairs += 1
    return dict(
        lanes=terminal,
        largest_individual_rss_kib=max(row["VmHWM"] for row in terminal),
        sum_of_individual_peaks_kib=sum(row["VmHWM"] for row in terminal),
        largest_near_simultaneous_sampled_sum_rss_kib=combined if pairs else None,
        paired_memory_samples=pairs,
        max_sample_separation_ns=MAX_SAMPLE_SEPARATION_NS,
    )
