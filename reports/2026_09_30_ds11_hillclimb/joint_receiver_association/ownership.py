"""Exact ownership alternatives for raw detections reused by track hypotheses."""
import itertools
import math
def alternatives(owners,max_states=256):
    keys=sorted(owners)
    if any(not owners[k] or len(set(owners[k]))!=len(owners[k]) for k in keys):raise ValueError('nonempty unique owners required')
    size=math.prod(len(owners[k]) for k in keys)
    if size>max_states:raise ValueError('ownership budget exceeded; do not silently discard alternatives')
    return [(dict(zip(keys,choice)),-math.log(size)) for choice in itertools.product(*(owners[k] for k in keys))]
