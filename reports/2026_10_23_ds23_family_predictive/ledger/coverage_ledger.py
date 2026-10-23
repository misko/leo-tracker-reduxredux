"""Research-only coverage ledger; never modifies fits or global helpers."""
from copy import deepcopy

def accepted_ids(rows):
    ids=set()
    for row in rows:
        if not row['compatible']:continue
        local=set(row['observation_ids'])
        if len(local)!=len(row['observation_ids']) or ids&local:
            raise ValueError('duplicate physical association ownership')
        ids.update(local)
    return ids

def enforce_rejected_ids(coverage,rejected_ids,parent_accepted_ids):
    """Drop whole association records that touch an explicit rejection ledger.

    Whole records are removed because their frozen quality statistics do not
    certify an arbitrary sliced subset. Original accepted IDs are inviolable.
    Fitting metadata and observation denominator are preserved verbatim.
    """
    rejected=set(rejected_ids);protected=set(parent_accepted_ids)
    if rejected&protected:raise ValueError('rejected IDs overlap original parent accepted IDs')
    original_rows=coverage['associations']['tracks'];before=accepted_ids(original_rows)
    if before!=set(coverage['accepted_observation_ids']) or len(before)!=coverage['associated']:
        raise ValueError('input coverage association IDs/count disagree')
    if not protected<=before:raise ValueError('input coverage already loses parent accepted IDs')
    rows=[r for r in original_rows if not rejected.intersection(r['observation_ids'])]
    after=accepted_ids(rows)
    if not protected<=after:raise ValueError('whole-record rejection would remove protected parent IDs')
    result=deepcopy(coverage)
    result['associations']['tracks']=deepcopy(rows)
    result.update(accepted_observation_ids=sorted(after),associated=len(after),
        percent=100*len(after)/coverage['total_GLRT'],associated_tracks=len(rows))
    return result

def coverage_with_ledger(coverage_function,*args,rejected_ids,parent_accepted_ids,**kwargs):
    """Apply a ledger to an existing coverage port without modifying it."""
    return enforce_rejected_ids(coverage_function(*args,**kwargs),rejected_ids,parent_accepted_ids)
