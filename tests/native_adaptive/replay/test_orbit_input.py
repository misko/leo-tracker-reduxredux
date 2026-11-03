import pytest
from leo.native_pipeline.orbit_input import catalogue_id, select_tles
from leo.native_pipeline.orbit_input import replace_authority_states
import struct


def test_catalogue_identity_and_alpha5():
    assert catalogue_id('44714')==44714
    assert catalogue_id('A0001')==100001
    with pytest.raises(ValueError):catalogue_id('I0001')
    with pytest.raises(ValueError):catalogue_id('00000')


def test_selection_order_and_missing_identity():
    a='1 44714'+' '*62;b='2 44714'+' '*62
    assert select_tles('NAME\n'+a+'\n'+b+'\n',[44714])=='1\n'+a+'\n'+b+'\n'
    with pytest.raises(ValueError,match='missing'):select_tles(a+'\n'+b,[44715])
    with pytest.raises(ValueError,match='duplicated'):select_tles(a+'\n'+b,[44714,44714])


def test_tle_pair_identity_must_agree():
    a='1 44714'+' '*62;b='2 44715'+' '*62
    with pytest.raises(ValueError,match='mismatched'):select_tles(a+'\n'+b,[44714])


def test_native_state_binding_rejects_wrong_epoch_and_memberships():
    meta={'start_utc_ns':100,'knot_start_s':0.,'knot_step_s':10.,'knot_count':2,'satellite_ids':[44714]}
    states=struct.pack('<12d',*range(12))
    payload=struct.pack('<5I2d',0x31434f4c,1,2,0,1,0.,10.)+b'\0'*48+struct.pack('<i',44714)+states
    assert replace_authority_states(payload,meta,states,meta)==payload
    with pytest.raises(ValueError,match='start_utc_ns'):replace_authority_states(payload,meta,states,{**meta,'start_utc_ns':101})
    corrupt=bytearray(payload);struct.pack_into('<I',corrupt,12,1)
    with pytest.raises(ValueError,match='response-bearing'):replace_authority_states(corrupt,meta,states,meta)
