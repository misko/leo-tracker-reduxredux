import numpy as np
import pytest
from probe_ds23_secondary_curves import peak_noise
from types import SimpleNamespace
import hashlib
import probe_ds23_secondary_curves as module


def test_weaker_peak_has_its_own_bounded_noise():
    metadata=dict(extra_parameter_BIC_gain=1,constant_radio_sigma_hz=100,floor_sigma_hz=30,strength_hz2=10000)
    assert peak_noise(metadata,1)>peak_noise(metadata,10)
    assert peak_noise(metadata,1e-9)==600
    assert peak_noise(metadata,1e9)==40
    metadata['extra_parameter_BIC_gain']=-1
    assert peak_noise(metadata,1)==100


@pytest.mark.parametrize('margin',[0,-1,np.nan,np.inf])
def test_bad_margin_rejected(margin):
    with pytest.raises(ValueError):peak_noise({},margin)


def test_fast_adapter_preserves_public_probe_identity_and_time(monkeypatch):
    probes=[dict(candidates=[dict(passed_fractional_margin_gate=True)]),
            dict(candidates=[dict(passed_fractional_margin_gate=False)])]
    evidence=SimpleNamespace(ids=('session:0:100','session:1:200'),time_s=np.array([1.25,2.25]))
    monkeypatch.setattr(module,'frequency_evidence',lambda d:(evidence,None,{}))
    document=dict(clock_anchor={},source=dict(probes=probes))
    source,rows=module.probe_authority(document)
    assert source is document['source'] and set(rows)=={0}
    assert rows[0]==dict(observation_id='sha256:'+hashlib.sha256(b'session:0:100').hexdigest(),time_s=1.25)
