from types import SimpleNamespace
import numpy as np
from predict02 import exclude_target, replace_noise


def test_whole_target_excluded_even_if_its_responses_change():
    target=dict(key='D',values=np.array([1.,2.,3.]))
    other=dict(key='O',values=np.array([4.,5.,6.]))
    assert exclude_target([target,other],'D')==[other]
    changed=dict(target,values=target['values']+1000)
    assert exclude_target([changed,other],'D')==[other]


def test_noise_replacement_is_research_only_and_does_not_mutate_original():
    old=dict(constant_radio_sigma_hz=70.,per_observation_noise_sigma_hz={'a':70.})
    scan=SimpleNamespace(fixed_window_noise=old,radio_sigma_hz=70.,fixed_window_noise_sha256='original',tracks=['unchanged'])
    model=dict(constant_radio_sigma_hz=60.,per_observation_noise_sigma_hz={'a':55.})
    changed=replace_noise(scan,model)
    assert changed.fixed_window_noise is model and changed.radio_sigma_hz==60.
    assert scan.fixed_window_noise is old and scan.radio_sigma_hz==70.
    assert changed.tracks is scan.tracks and scan.fixed_window_noise_sha256=='original'
