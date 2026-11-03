import importlib.util
from pathlib import Path
import struct

import pytest


def module():
    path = Path(__file__).resolve().parents[3]/'tools/diagnose_native_position_choice.py'
    spec = importlib.util.spec_from_file_location('position_choice',path)
    value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_replacing_sites_preserves_track_masks_and_orbits():
    m=module()
    tail=struct.pack('<2I',6,3)+b'x'*(17*6)+b'orbit-bank'
    original=struct.pack('<5I2d',0x31434f4c,1,2,1,1,-60.,10.)+bytes(48)+tail
    result,weights=m.replace_sites(original,[[1.,2.,3.,4.,5.,6.]]*2)
    assert weights==[3]
    assert result[36+96:]==tail
    assert struct.unpack_from('<5I',result)[4]==2


def test_contributions_apply_cap_before_difference():
    m=module()
    points=[{'tracks':[{'held_hz':900},{'held_hz':100}]},
            {'tracks':[{'held_hz':1000},{'held_hz':200}]}]
    rows=m.contribution_rows(points,[1,3])
    assert rows[0]['track_index']==1
    assert rows[0]['weighted_mse_delta_arm_minus_server']==22500
    assert rows[1]['weighted_mse_delta_arm_minus_server']==0
    with pytest.raises(ValueError,match='dimensions'):
        m.contribution_rows(points,[1])


def test_site_origin_uses_wgs84_and_unit_up():
    m=module()
    assert m.site(0,0,0,0)==[6378.137,0,0,1,0,0]
