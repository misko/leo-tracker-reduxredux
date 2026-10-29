import pytest
from debug_fast_graph_unassociated import read,write
from finalize_geometry_limited_annotation import finalize


def test_stopped_run_is_never_relabelled_complete_and_invalid_group_proves_no_identity(tmp_path):
    write(tmp_path/'protocol.json',dict(job={},target=dict(track_id='t',component='curve'),seed_list=[1,2,3]))
    terminal=tmp_path/'terminal.json';write(terminal,dict(status='timeout',track_id='t'))
    with pytest.raises(ValueError,match='unfinished fits'):finalize(tmp_path,terminal)
    assert not (tmp_path/'result.json').exists()
    write(tmp_path/'seed-2.json',dict(status='insufficient_group_support'))
    r=finalize(tmp_path,terminal)
    assert r['annotation']['status']=='insufficient_partitions' and r['annotation']['norad'] is None
    assert r['geometry_certificate']['maximum_usable_partitions']==2
    assert not r['original_execution_completed'] and r['remaining_candidate_fits_not_executed']
    assert read(terminal)['status']=='timeout'
    with pytest.raises(ValueError,match='never replace'):finalize(tmp_path,terminal)
