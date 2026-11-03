import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location('stability_test', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_stable_tone_and_alternating_disagreement_use_only_fit_symbols():
    _, _, fit, *_ = run.wave.load_waveform_helpers()
    symbols = np.arange(300)
    stable = np.broadcast_to(np.exp(2j*np.pi*137*symbols*4.4e-6)[None,:,None], (8,300,2)).copy()
    a = run.metrics(stable, np.arange(20,220), fit)
    assert abs(a['full_native_hz']-137) < .01
    assert a['alternating_disagreement_hz'] < .01
    assert a['coherent_energy_fraction'] > .999999
    stable[:,220:] = 1000+300j
    assert run.metrics(stable, np.arange(20,220), fit) == a
    stable[1::2] = np.exp(-2j*np.pi*137*symbols*4.4e-6)[None,:,None]
    b = run.metrics(stable, np.arange(20,220), fit)
    assert abs(b['alternating_disagreement_hz']-274) < .01
