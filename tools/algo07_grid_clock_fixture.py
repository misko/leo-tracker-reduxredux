"""Research-only injected grid clock; never used by production publication.

The sampler checks its clock once at start, before each paired location, and at
return. This fixture controls that logical admission boundary. It does not
alter scores, endpoint selection or the independently enforced wall timeout.
"""

import time


class LocationClock:
    def __init__(self, locations, deadline):
        if type(locations) is not int or not 0 <= locations <= 1000 or deadline <= 0:
            raise ValueError('Explicit bounded logical location budget required')
        self.locations = locations
        self.deadline = deadline
        self.calls = 0

    def __call__(self):
        call = self.calls
        self.calls += 1
        return 0. if call <= self.locations else self.deadline


def controlled_sampler(original, locations, receipts):
    """Wrap only the diagnostic sampler in an isolated test process."""
    def sample(score, endpoints, **kwargs):
        if 'clock' in kwargs:
            raise ValueError('Caller supplied another grid clock')
        clock = LocationClock(locations, kwargs.get('maximum_seconds', 30.))
        began = time.monotonic()
        result = original(score, endpoints, clock=clock, **kwargs)
        expected = min(locations, result['planned_points'])
        if result['evaluated_points'] != expected:
            raise ValueError('Sampler clock protocol or planned work changed')
        receipts.append(dict(kind='controlled-logical-grid-clock',
                             requested_paired_locations=locations,
                             completed_paired_locations=result['evaluated_points'],
                             planned_paired_locations=result['planned_points'],
                             complete=result['complete'], clock_calls=clock.calls,
                             real_wall_seconds=time.monotonic() - began,
                             grid_elapsed_seconds_is_synthetic=True,
                             production_deadline_behavior_qualified=False))
        return result
    return sample
