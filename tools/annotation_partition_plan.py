"""Verify a frozen timestamp-only partition plan before any frequency fitting."""
import hashlib
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.grouped_prediction import geometry_partition_schedule


def require_distinct_annotation(result,protocol):
    """Different seed labels alone do not establish distinct target holdouts."""
    plan=protocol.get('partition_plan') or {};schedule=plan.get('schedule') or {}
    selected=schedule.get('selected',[])
    signatures={tuple(sorted(r['target_held_blocks'])) for r in selected}
    if (not schedule.get('ready') or len(selected)!=3 or len(signatures)!=3
            or [f['seed'] for f in result['folds']]!=[r['seed'] for r in selected]):
        raise ValueError('three distinct timestamp-selected target holdouts required')


def selected_seeds(path,track_id,times,focus,default,*,distinct=False):
    if distinct:
        if path is not None:raise ValueError('choose a saved audit or a new distinct schedule')
        pool=[20261029,94721,4081]+np.random.default_rng(20261029).integers(0,2**31-1,64).tolist()
        plan=geometry_partition_schedule(times,focus,seeds=pool)
        receipt=dict(seed_pool=pool,schedule=plan,selection_uses_timestamps_only=True,
            geometry_only_early_exit=not plan['ready'],target_timestamps_sha256=hashlib.sha256(np.asarray(focus,dtype='<f8').tobytes()).hexdigest())
        return ([r['seed'] for r in plan['selected']] if plan['ready'] else []),receipt
    if path is None:return list(default),None
    audit=read(path);row=next(r for r in audit['rows'] if r['track_id']==track_id)
    if not np.array_equal(np.asarray(row['times_s']),focus):raise ValueError('partition audit target timestamps changed')
    plan=geometry_partition_schedule(times,focus,seeds=audit['seed_pool'])
    if plan!=row['schedule'] or not plan['ready']:raise ValueError('partition audit is not a matching usable plan')
    return [r['seed'] for r in plan['selected']],dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target_holdouts=[r['target_held_blocks'] for r in plan['selected']],selection_uses_timestamps_only=True)
