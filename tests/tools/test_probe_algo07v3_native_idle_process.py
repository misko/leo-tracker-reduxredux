import pytest
from probe_algo07v3_native_idle_process import routing

from leo.operations import localization_v3_parallel as parallel


@pytest.mark.parametrize('candidate',[False,True])
def test_native_routing_exact_and_restored(candidate):
    original = parallel.map_initial_branches
    tasks = [(0,'c0'),(0,'fitted_c')]
    rows = []
    with routing(candidate,rows):
        result = parallel.map_initial_branches(lambda item:item,tasks)
    assert result==tasks and parallel.map_initial_branches is original
    assert len(rows)==1 and rows[0]['complete']
    assert len(rows[0]['tasks']) == (2 if candidate else 0)


def test_routing_failure_restores_original():
    original = parallel.map_initial_branches
    rows = []
    with pytest.raises(ValueError),routing(True,rows):
        parallel.map_initial_branches(lambda x:x,[(1,'c0')])
    assert parallel.map_initial_branches is original
    assert not rows[0]['complete']
