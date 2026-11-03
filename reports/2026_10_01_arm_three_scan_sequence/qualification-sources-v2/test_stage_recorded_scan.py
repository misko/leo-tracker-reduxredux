import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from stage_recorded_scan import validated_files


def fixture(tmp_path):
    raw = bytes(2400000)
    (tmp_path/'visit-000000.ci16').write_bytes(raw)
    return [{'visit':0,'path':'visit-000000.ci16','size_bytes':len(raw),
             'raw_sha256':hashlib.sha256(raw).hexdigest()}]


def test_complete_original_bytes_required(tmp_path):
    rows=fixture(tmp_path)
    assert validated_files(tmp_path,rows)==['visit-000000.ci16']
    with (tmp_path/rows[0]['path']).open('r+b') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='hash differs'):validated_files(tmp_path,rows)


@pytest.mark.parametrize('fault',['path','count','partial','symlink'])
def test_unsafe_or_partial_inventory_rejected(tmp_path,fault):
    rows=fixture(tmp_path);path=tmp_path/rows[0]['path']
    if fault=='path':rows[0]['path']='../escape'
    elif fault=='count':rows[0]['visit']=1
    elif fault=='partial':path.write_bytes(bytes(400000))
    else:
        path.rename(tmp_path/'original');path.symlink_to(tmp_path/'original')
    with pytest.raises(ValueError):validated_files(tmp_path,rows)
