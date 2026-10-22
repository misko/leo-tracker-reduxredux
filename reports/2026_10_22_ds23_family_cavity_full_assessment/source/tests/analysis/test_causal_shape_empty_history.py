import hashlib
from types import SimpleNamespace
import numpy as np
import prototype_s01_causal_shape as m


def test_absent_previous_element_uses_declared_unavailable_history_without_propagation(tmp_path,monkeypatch):
    path=tmp_path/'previous.tle';path.write_text('historical catalogue fixture')
    scan=SimpleNamespace(norads=np.array([100,200]),receipt=dict(previous_tle_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
        sky=dict(time_s=np.arange(3.),position_km=np.ones((2,3,3)),velocity_km_s=np.full((2,3,3),2.)))
    monkeypatch.setattr(m,'parse_element_sets',lambda _:SimpleNamespace(satellite_numbers=(),satellites=()))
    monkeypatch.setattr(m,'ecef_states',lambda *_:(_ for _ in ()).throw(AssertionError('empty historical set must not be propagated')))
    previous,available,alignment=m.previous_bank(scan,[1],previous_path=path)
    assert available==set() and alignment=={}
    np.testing.assert_array_equal(previous['position_km'],scan.sky['position_km'][[1]])
    np.testing.assert_array_equal(previous['velocity_km_s'],scan.sky['velocity_km_s'][[1]])
    previous['position_km'][0,0,0]=99
    assert scan.sky['position_km'][1,0,0]==1
