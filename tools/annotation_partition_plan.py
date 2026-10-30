"""Verify a frozen timestamp-only partition plan before any frequency fitting."""
import hashlib
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.grouped_prediction import geometry_partition_schedule,shifted_geometry_partition_schedule,replay_split,grouped_split


def require_distinct_annotation(result,protocol):
    """Different seed labels alone do not establish distinct target holdouts."""
    plan=protocol.get('partition_plan') or {};schedule=plan.get('schedule') or {}
    selected=schedule.get('selected',[])
    if schedule.get('partition_scheme')=='shifted_origin_v1':
        focus=np.asarray(plan['target_times_s'],dtype='<f8')
        if hashlib.sha256(focus.tobytes()).hexdigest()!=plan['target_timestamps_sha256']:raise ValueError('shifted target timestamps changed')
        if not schedule.get('ready') or len(selected)!=3 or len(result['folds'])!=3:raise ValueError('three distinct shifted target holdouts required')
        signatures=[]
        for f,r in zip(result['folds'],selected,strict=True):
            if f['seed']!=r['seed'] or any(f['split'].get(k)!=r.get(k) for k in ('held_blocks','block_origin_s','block_s','guard_s')):
                raise ValueError('shifted annotation does not replay its frozen schedule')
            train,held=replay_split(focus,f['split']);signature=tuple(np.flatnonzero(held).tolist());signatures.append(signature)
            if list(signature)!=r['target_held_indices'] or train.sum()<8 or held.sum()<4 or r['block_s']!=12 or r['guard_s']!=2:
                raise ValueError('shifted schedule changes physical support or grouping policy')
        if len(set(signatures))!=3:raise ValueError('three distinct shifted target holdouts required')
        return
    signatures={tuple(sorted(r['target_held_blocks'])) for r in selected}
    if (not schedule.get('ready') or len(selected)!=3 or len(signatures)!=3
            or [f['seed'] for f in result['folds']]!=[r['seed'] for r in selected]):
        raise ValueError('three distinct timestamp-selected target holdouts required')


def selected_seeds(path,track_id,times,focus,default,*,distinct=False,shifted_origin=False):
    if shifted_origin and not distinct:raise ValueError('shifted origins require a distinct timestamp-only schedule')
    if distinct:
        if path is not None:raise ValueError('choose a saved audit or a new distinct schedule')
        pool=[20261029,94721,4081]+np.random.default_rng(20261029).integers(0,2**31-1,64).tolist()
        plan=(shifted_geometry_partition_schedule if shifted_origin else geometry_partition_schedule)(times,focus,seeds=pool)
        receipt=dict(seed_pool=pool,schedule=plan,selection_uses_timestamps_only=True,
            geometry_only_early_exit=not plan['ready'],target_timestamps_sha256=hashlib.sha256(np.asarray(focus,dtype='<f8').tobytes()).hexdigest())
        if shifted_origin:receipt['target_times_s']=np.asarray(focus).tolist()
        return ([r['seed'] for r in plan['selected']] if plan['ready'] else []),receipt
    if path is None:return list(default),None
    audit=read(path);row=next(r for r in audit['rows'] if r['track_id']==track_id)
    if not np.array_equal(np.asarray(row['times_s']),focus):raise ValueError('partition audit target timestamps changed')
    plan=geometry_partition_schedule(times,focus,seeds=audit['seed_pool'])
    if plan!=row['schedule'] or not plan['ready']:raise ValueError('partition audit is not a matching usable plan')
    return [r['seed'] for r in plan['selected']],dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target_holdouts=[r['target_held_blocks'] for r in plan['selected']],selection_uses_timestamps_only=True)


def planned_split(times,focus,seed,plan):
    schedule=(plan or {}).get('schedule',{})
    if schedule.get('partition_scheme')!='shifted_origin_v1':return grouped_split(times,focus,seed=seed)
    if hashlib.sha256(np.asarray(focus,dtype='<f8').tobytes()).hexdigest()!=plan['target_timestamps_sha256']:
        raise ValueError('shifted target timestamps changed')
    receipt=next(r for r in schedule['selected'] if r['seed']==seed)
    train,held=replay_split(times,receipt)
    if train.sum()!=receipt['training_points'] or held.sum()!=receipt['held_points']:
        raise ValueError('shifted scan support changed')
    return train,held,receipt
