import hashlib
import json
import pytest

from export_ds23_converter_geometry import parse_metadata


def test_fast_reference_hypothesis_is_preserved_without_inventing_a_band_switch():
    target=dict(channel=8,edge='upper',rf_center_hz=12_690_312_500,
        lnb_lo_hz=9_750_000_000,if_center_hz=2_940_312_500,rf_mapping_authority='hypothesis')
    raw=dict(configuration=dict(sample_rate_hz=2_500_000,targets=[target]))
    result=parse_metadata(raw)
    assert result['targets'][0]['lnb_lo_hz']==9_750_000_000
    assert result['targets'][0]['rf_mapping_authority']=='hypothesis'
    raw['configuration']['targets'][0]['if_center_hz']+=1
    with pytest.raises(ValueError,match='frequency equation'):
        parse_metadata(raw)


def test_adaptive_envelope_digest_is_checked_before_using_converter_geometry():
    target=dict(channel=1,edge='lower',rf_center_hz=10_709_687_500,if_center_hz=959_687_500)
    body=dict(receipt=dict(plan=dict(geometry=dict(lnb_lo_hz=9_750_000_000,sample_rate_hz=2_500_000,
        profiles=[dict(target=target)]))))
    payload=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    raw=dict(manifest=body,sha256='sha256:'+hashlib.sha256(payload).hexdigest())
    assert parse_metadata(raw)['targets'][0]['lnb_lo_hz']==9_750_000_000
    body['receipt']['plan']['geometry']['sample_rate_hz']=10_000_000
    with pytest.raises(ValueError,match='binding changed'):
        parse_metadata(raw)
