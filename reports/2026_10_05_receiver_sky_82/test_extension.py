"""Pure metadata/control tests: no hardware, QNAP or database access."""
import copy
import pytest
from extend_cohort import select


def rows(n):
    return [dict(session_id=f'scan-{i:03}', capture_start_ns=i*100,
                 capture_end_ns=i*100+10) for i in range(n)]


def test_metadata_selection_deterministic_disjoint_and_nonmutating():
    pool = rows(100)
    before = copy.deepcopy(pool)
    original = [pool[20], pool[70]]
    result = select(original, pool)
    assert result == select(list(reversed(original)), list(reversed(pool)))
    assert pool == before
    assert len(result) == len({r['session_id'] for r in result}) == 64
    assert not {r['session_id'] for r in result} & {r['session_id'] for r in original}
    assert [r['label'] for r in result] == [f'N{i:02}' for i in range(17, 81)]
    assert sorted(r['selection_rank'] for r in result) == list(range(1, 65))


def test_fit_metrics_cannot_affect_selection():
    pool = rows(100)
    expected = [r['session_id'] for r in select([pool[0]], pool)]
    for i, r in enumerate(pool):
        r.update(rms_hz=i*100, coverage=1-i/100, position_error_m=i)
    assert [r['session_id'] for r in select([pool[0]], pool)] == expected


def test_duplicate_or_insufficient_sessions_fail_closed():
    with pytest.raises(ValueError, match='duplicate'):
        select(rows(1), rows(100)+[rows(100)[2]])
    with pytest.raises(ValueError, match='insufficient'):
        select(rows(1), rows(10))


def test_temporal_bootstrap_preserves_point_estimates_and_counts_clusters():
    import numpy as np
    from sky_extension import temporal_kernel, prepare, kernel
    events=[]
    for s in range(10):
        for j in range(6):
            events.append(dict(scan=f's{s}',satellite=j,time_s=1.,channel=1,
                               east=0.,north=0.,up=1.,outcome=(s+j)%3))
    epochs={f's{s}':(s//2)*3*3600*10**9 for s in range(10)}
    grid=np.array([[0.,0.,1.],[1.,0.,0.]])
    grouped=temporal_kernel(events,grid,epochs,bootstrap=20)
    original=kernel(prepare(events),grid,bootstrap=0)
    np.testing.assert_allclose(grouped['probability'],original['probability'],equal_nan=True)
    assert grouped['total_scans']==10 and grouped['total_time_blocks']==5
    assert grouped['time_block_count'].tolist()==[5,0]
    assert grouped['supported'].tolist()==[True,False]


def test_adjacent_scans_do_not_count_as_independent_sky_support():
    import numpy as np
    from sky_extension import temporal_kernel
    events=[dict(scan=f's{s}',satellite=j,time_s=1.,channel=1,
                 east=0.,north=0.,up=1.,outcome=s%3) for s in range(10) for j in range(6)]
    result=temporal_kernel(events,np.array([[0.,0.,1.]]),{f's{s}':s*100000 for s in range(10)},bootstrap=10)
    assert result['total_time_blocks']==1
    assert not result['supported'][0]


def test_cached_port_only_reuses_metadata_not_iq():
    from cached_refinement import CachedReadPort
    class Store:
        inspections=0
        reads=0
        def inspect(self, session):
            self.inspections+=1
            return dict(session=session)
        def read_visit_ci16(self, published, ordinal):
            self.reads+=1
            return published['session'],ordinal
    store=Store();port=CachedReadPort(store)
    a=port.inspect('a');assert port.inspect('a') is a
    assert port.inspect('b')['session']=='b'
    assert store.inspections==2
    assert port.read_visit_ci16(a,0)==('a',0)
    assert port.read_visit_ci16(a,1)==('a',1)
    assert store.reads==2


def test_renderer_wont_label_missing_results_complete(tmp_path, monkeypatch):
    import render_maps
    monkeypatch.setattr(render_maps,'WORK',tmp_path)
    with pytest.raises(ValueError,match='still pending'):
        render_maps.ready_records({'original_labels':[],'new_labels':['N17']})
    with pytest.raises(ValueError,match='no additional'):
        render_maps.ready_records({'original_labels':[],'new_labels':['N17']},allow_partial=True)
