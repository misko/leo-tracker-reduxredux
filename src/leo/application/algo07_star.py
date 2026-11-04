"""One bounded coordinator over the existing stage ports; no scientific changes."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

ALGORITHMS = tuple(f'ALGO{i:02d}' for i in range(2, 8))


@dataclass(frozen=True)
class Stage:
    algorithm: str
    maximum_seconds: int
    completed: Callable[[Any], bool]
    execute: Callable[[Any], Any]


def run(stages: Sequence[Stage], initial, *, through='ALGO07', maximum_seconds=1800,
        clock=time.monotonic):
    """Checkpoint between stages rather than shrink their production budgets.

    Ports verify/reuse completed checkpoints and perform their own bounded job
    execution, ownership, terminal validation and failure handling. This method
    neither catches scientific failures nor turns an incomplete stage into a win.
    """
    if tuple(s.algorithm for s in stages) != ALGORITHMS or through not in ALGORITHMS:
        raise ValueError('The complete ordered ALGO02–07 stage graph is required')
    if type(maximum_seconds) is not int or not 0 < maximum_seconds <= 1800:
        raise ValueError('Coordinator invocation must be bounded to 30 minutes')
    if any(type(s.maximum_seconds) is not int or not 1 <= s.maximum_seconds <= 1200
           for s in stages):
        raise ValueError('Explicit production stage budgets in 1..1200 seconds required')
    began = clock()
    incumbent = initial
    timings = []
    for stage in stages:
        # Leave room for the existing adapter's 15-second shutdown allowance and
        # terminal publication. Never shorten a scientific stage to fill a slice.
        if (not stage.completed(incumbent)
                and maximum_seconds-(clock()-began) < stage.maximum_seconds+45):
            return dict(state='checkpointed', next_stage=stage.algorithm,
                        stages=timings, incumbent=incumbent)
        start = clock()
        incumbent = stage.execute(incumbent)
        if incumbent is None:
            return dict(state='owned_elsewhere', next_stage=stage.algorithm,
                        stages=timings, incumbent=None)
        timings.append(dict(algorithm=stage.algorithm, wall_seconds=clock()-start))
        if incumbent['state'] != 'complete':
            return dict(state='stage_failed', next_stage=None, stages=timings,
                        incumbent=incumbent)
        if stage.algorithm == through:
            return dict(state='scientific_complete' if through == 'ALGO07' else 'checkpointed',
                        next_stage=None if through == 'ALGO07' else
                        ALGORITHMS[ALGORITHMS.index(through)+1],
                        stages=timings, incumbent=incumbent)
    raise AssertionError('Unreachable stage graph')
