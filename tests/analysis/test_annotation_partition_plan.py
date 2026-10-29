import numpy as np
import pytest
from annotation_partition_plan import selected_seeds
from debug_fast_graph_unassociated import write
from leo.analysis.research.grouped_prediction import geometry_partition_schedule


def test_plan_must_reproduce_geometry_before_frequency_fits(tmp_path):
    t=np.arange(0.,120.,.5);focus=t[(t>20)&(t<80)];seeds=list(range(64));plan=geometry_partition_schedule(t,focus,seeds=seeds)
    p=tmp_path/'audit.json';write(p,dict(seed_pool=seeds,rows=[dict(track_id='t',times_s=focus,schedule=plan)]))
    chosen,receipt=selected_seeds(p,'t',t,focus,[7,8,9])
    assert chosen==[r['seed'] for r in plan['selected']] and receipt['selection_uses_timestamps_only']
    with pytest.raises(ValueError,match='timestamps'):selected_seeds(p,'t',t,focus+.1,[7,8,9])
    with pytest.raises(ValueError,match='matching'):selected_seeds(p,'t',np.r_[t,240.],focus,[7,8,9])


def test_on_demand_schedule_and_geometry_only_exit():
    times=np.arange(0.,120.,.5);focus=times[(times>20)&(times<80)]
    chosen,receipt=selected_seeds(None,'t',times,focus,[7,8,9],distinct=True)
    assert len(chosen)==3 and not receipt['geometry_only_early_exit']
    assert len({tuple(r['target_held_blocks']) for r in receipt['schedule']['selected']})==3
    chosen,receipt=selected_seeds(None,'t',times,focus[:5],[7,8,9],distinct=True)
    assert chosen==[] and receipt['geometry_only_early_exit']
    assert selected_seeds(None,'t',times,focus,[7,8,9])==([7,8,9],None)
    with pytest.raises(ValueError,match='choose'):selected_seeds('audit','t',times,focus,[7,8,9],distinct=True)
