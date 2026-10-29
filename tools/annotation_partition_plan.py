"""Verify a frozen timestamp-only partition plan before any frequency fitting."""
import hashlib
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.grouped_prediction import geometry_partition_schedule


def selected_seeds(path,track_id,times,focus,default):
    if path is None:return list(default),None
    audit=read(path);row=next(r for r in audit['rows'] if r['track_id']==track_id)
    if not np.array_equal(np.asarray(row['times_s']),focus):raise ValueError('partition audit target timestamps changed')
    plan=geometry_partition_schedule(times,focus,seeds=audit['seed_pool'])
    if plan!=row['schedule'] or not plan['ready']:raise ValueError('partition audit is not a matching usable plan')
    return [r['seed'] for r in plan['selected']],dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target_holdouts=[r['target_held_blocks'] for r in plan['selected']],selection_uses_timestamps_only=True)
