"""Native isolated comparison of a process helper in the last initial-search fit."""

import time
from contextlib import contextmanager
from pathlib import Path

from probe_algo07v3_idle_process import IdleProcessDerivatives
from probe_algo07v3_native_gradients import main
from profile_algo07v3 import cpu

from leo.cli.algo07v3 import worker, write
from leo.operations import localization_v3_parallel as parallel


@contextmanager
def routing(enabled, rows):
    original = parallel.map_initial_branches
    def mapped(operation, items):
        coordinator = IdleProcessDerivatives()
        began, before = time.perf_counter(), cpu()
        complete = False
        try:
            value = coordinator.map(operation, items) if enabled else original(operation, items)
            complete = True
            return value
        finally:
            after = cpu()
            rows.append(dict(candidate=enabled, complete=complete,
                             seconds=time.perf_counter()-began,
                             cpu_seconds=sum(b-a for a,b in zip(before,after,strict=True)),
                             tasks=coordinator.records))
    parallel.map_initial_branches = mapped
    try:
        yield
    finally:
        parallel.map_initial_branches = original


def measured_worker(root, variant):
    rows = []
    try:
        with routing(variant=='candidate', rows):
            return worker(root/'request.json',root/'worker.json',False)
    finally:
        write(root/'initial-tasks.json',rows)


if __name__ == '__main__':
    raise SystemExit(main(worker_operation=measured_worker, entry_path=Path(__file__),
        runner_path=Path('reports/2026_11_06_algo07v3_idle_process/isolate.sh'),
        extra_paths=(Path('tools/probe_algo07v3_idle_derivatives.py'),
                     Path('tools/probe_algo07v3_idle_process.py'),
                     Path('tools/check_algo07v3_scan_likelihood.py')),
        counter_events=('cpu_core/cycles/', 'cpu_core/instructions/', 'task-clock')))
