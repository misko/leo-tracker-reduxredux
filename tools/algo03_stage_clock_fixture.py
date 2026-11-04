"""Research-only ALGO03 admission clock with separately bounded real children.

Use only inside an isolated diagnostic process with an external wall deadline.
The installed worker and its child commands remain unchanged; only its local
monotonic clock uses a declared stage-duration schedule. Never use the resulting
synthetic timing receipts to qualify ordinary production deadline behavior.
"""
import math
import time
from pathlib import Path
from types import SimpleNamespace


class StageClock:
    def __init__(self, schedule, maximum_seconds, stop_after):
        if (type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 1200
                or not schedule or len(schedule) > 128):
            raise ValueError('Bounded worker and explicit nonempty schedule required')
        if any(set(row) != {'name', 'script', 'seconds'}
               or not isinstance(row['name'], str) or not row['name']
               or not isinstance(row['script'], str) or not row['script'].endswith('.py')
               or Path(row['script']).name != row['script']
               or type(row['seconds']) not in (float, int)
               or not math.isfinite(row['seconds']) or not 0 <= row['seconds'] < 600
               for row in schedule):
            raise ValueError('Known stage names, script basenames and finite durations required')
        if len({r['name'] for r in schedule}) != len(schedule):
            raise ValueError('Stage names must be unique')
        if stop_after is not None and stop_after != schedule[-1]['name']:
            raise ValueError('Cancellation fixture must end at its last planned child')
        self.schedule = [dict(row) for row in schedule]
        self.maximum_seconds = maximum_seconds
        self.stop_after = stop_after
        self.index = 0
        self.now = 0.
        self.jump_calls = None
        self.synthetic_durations = []

    def __call__(self):
        if self.jump_calls is not None:
            if self.jump_calls == 0:
                self.now = max(self.now, min(600., self.maximum_seconds * .7) + .001)
                self.jump_calls = None
            else:
                self.jump_calls -= 1
        return self.now

    def expected(self, command, log):
        if self.index >= len(self.schedule):
            raise ValueError('Unexpected extra numerical child')
        row = self.schedule[self.index]
        if (Path(log.name).stem != row['name'] or len(command) < 3
                or command[1] != '-B' or Path(command[2]).name != row['script']):
            raise ValueError('Numerical child order or command changed')
        return row

    def completed(self):
        row = self.schedule[self.index]
        before = self.now
        self.now += row['seconds']
        self.synthetic_durations.append(self.now - before)
        self.index += 1
        if row['name'] == self.stop_after:
            # First read closes the completed child's duration; the following
            # read is discovery admission (or final elapsed accounting).
            self.jump_calls = 1


def run_controlled(worker, output, maximum_seconds, schedule, *, stop_after=None):
    """Run the real worker control flow and delegate every child to its executor."""
    if worker.POLICY != 'algo03-bounded-recovery-v1':
        raise ValueError('Unexpected recovery policy')
    clock = StageClock(schedule, maximum_seconds, stop_after)
    original_time, original_execute = worker.time, worker.execute
    children = []

    def execute(command, *, log, timeout):
        row = clock.expected(command, log)
        record = dict(name=row['name'], script=row['script'], real_timeout_seconds=timeout)
        began = time.monotonic()
        try:
            code = original_execute(command, log=log, timeout=timeout)
            record['returncode'] = code
            if code == 0:
                clock.completed()
            return code
        except BaseException as error:
            record['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            record['real_wall_seconds'] = time.monotonic() - began
            children.append(record)

    began = time.monotonic()
    try:
        worker.time = SimpleNamespace(monotonic=clock)
        worker.execute = execute
        result = worker.run(output, maximum_seconds)
    finally:
        worker.time, worker.execute = original_time, original_execute
    if (clock.index != len(schedule) or len(children) != len(schedule)
            or [s['name'] for s in result['stages']] != [s['name'] for s in schedule]
            or any(s['status'] != 'complete' or s['returncode'] != 0 for s in result['stages'])
            or [s['seconds'] for s in result['stages']] != clock.synthetic_durations):
        raise ValueError('Controlled recovery did not execute the declared complete work')
    receipt = dict(kind='controlled-algo03-stage-clock', children=children,
                   schedule=[dict(r) for r in schedule], stop_after=stop_after,
                   real_wall_seconds=time.monotonic() - began,
                   synthetic_elapsed_seconds=result['seconds'],
                   clock_elapsed_seconds_is_synthetic=True,
                   production_deadline_behavior_qualified=False)
    return result, receipt
