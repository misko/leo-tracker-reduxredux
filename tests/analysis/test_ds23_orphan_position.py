import json
import pytest

from probe_ds23_orphan_position import existing_node


def test_resuming_grid_reuses_only_the_identical_completed_scientific_request(tmp_path):
    path=tmp_path/'point.json'
    path.write_text(json.dumps(dict(case='C',level=0,index=1,point=[2.,3.],high_accuracy=False,status='complete')))
    assert existing_node(path,('C',0,1,[2.,3.],False))['reused_sha256']
    with pytest.raises(ValueError,match='frozen request'):
        existing_node(path,('C',0,1,[2.,4.],False))
