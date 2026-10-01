"""Validated scan-identity transfer from two disjoint pair states to a quad."""
import numpy as np
from leo.analysis.localization_window_starts import constituent_window_starts


def quad_starts(pair_states, pair_scans, pair_columns, target_scans, target_columns, dimension):
    if len(pair_states)!=2 or len(pair_scans)!=2 or len(pair_columns)!=2:
        raise ValueError('exactly two constituent pairs required')
    if len(target_scans)!=4 or len(set(target_scans))!=4 or len(target_columns)!=4:
        raise ValueError('four unique target scans required')
    local={};positions={}
    for raw_state,scans,maps in zip(pair_states,pair_scans,pair_columns,strict=True):
        state=np.asarray(raw_state,dtype=float)
        if state.ndim!=1 or not np.all(np.isfinite(state)) or len(scans)!=2 or len(maps)!=2:
            raise ValueError('invalid pair state or scan bindings')
        seen={0,1}
        for scan,raw_map in zip(scans,maps,strict=True):
            mapping=np.asarray(raw_map)
            if mapping.ndim!=1 or mapping.dtype.kind not in 'iu' or len(mapping)<2:
                raise ValueError('invalid pair map')
            if not np.array_equal(mapping[:2],[0,1]) or np.any(mapping<0) or np.any(mapping>=len(state)):
                raise ValueError('invalid pair position or map bounds')
            nuisance=mapping[2:].tolist()
            if len(set(nuisance))!=len(nuisance) or seen.intersection(nuisance):
                raise ValueError('overlapping pair nuisance columns')
            if scan in local:raise ValueError('duplicate constituent scan')
            seen.update(nuisance);local[scan]=state[mapping].copy();positions[scan]=state[:2].copy()
        if seen!=set(range(len(state))):raise ValueError('incomplete pair map')
    if set(local)!=set(target_scans):raise ValueError('constituent/target scan mismatch')
    # Require the fixed disjoint chronological AB/CD pairing, regardless of input ordering.
    expected={frozenset(target_scans[:2]),frozenset(target_scans[2:])}
    if {frozenset(s) for s in pair_scans}!=expected:raise ValueError('constituents must be target AB/CD')
    starts=constituent_window_starts([local[s] for s in target_scans],target_columns,
        np.array([positions[target_scans[0]],positions[target_scans[2]]]),dimension)
    return starts


def remaining_quad_budget(pair_launch_totals):
    values=np.asarray(pair_launch_totals,dtype=float)
    if values.shape!=(2,) or not np.all(np.isfinite(values)) or np.any(values<0):
        raise ValueError('two finite nonnegative pair launch totals required')
    cost=float(values.sum())
    return cost,360.-cost
