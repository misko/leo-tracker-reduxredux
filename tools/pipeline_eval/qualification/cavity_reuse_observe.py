"""Validate the capped process and execute the receiver's public entry unchanged."""

import json
import os
import resource
import runpy
import sys
from pathlib import Path
from time import perf_counter


def emit(label, value):
    print(label + " " + json.dumps(value), file=sys.stderr, flush=True)


def measured(unit, cpu, root, flags):
    text = Path("/proc/self/cgroup").read_text().strip()
    if not text.startswith("0::") or "\n" in text:
        raise ValueError("unified cgroup membership is required")
    group = Path("/sys/fs/cgroup") / text[3:].lstrip("/")

    def read(name):
        return int((group / name).read_text())

    memory, swap = read("memory.max"), read("memory.swap.max")
    if (
        group.name != unit + ".service"
        or os.sched_getaffinity(0) != {cpu}
        or (memory != 512 * 1024**2 or swap or os.nice(0) < 10)
    ):
        raise ValueError("effective service limits differ from the locked qualification")
    emit("proof", dict(cgroup=text[3:], cpu=cpu, nice=os.nice(0), memory=memory, swap=swap))
    begin = perf_counter()
    executable = str(root / "__main__.py")
    sys.argv = [executable, *flags]
    runpy.run_path(executable, run_name="__main__")
    origins = {
        name: str(Path(module.__file__).resolve())
        for name, module in sys.modules.items()
        if name.partition(".")[0] in {"leo", "tools"} and getattr(module, "__file__", None)
    }
    if not all(Path(path).is_relative_to(root) for path in origins.values()):
        raise ValueError("the standalone solve imported a project module outside its bundle")
    counters = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
    events = dict(line.split() for line in (group / "memory.events").read_text().splitlines())
    emit("origins", origins)
    emit(
        "finish",
        dict(
            measured_wall_s=perf_counter() - begin,
            cgroup_cpu_s=int(counters["usage_usec"]) / 1e6,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            cgroup_peak=read("memory.peak"),
            swap_current=read("memory.swap.current"),
            oom_kill=int(events["oom_kill"]),
        ),
    )


if __name__ == "__main__":
    measured(sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:])
