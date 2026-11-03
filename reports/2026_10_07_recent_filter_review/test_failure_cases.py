import importlib.util
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('failure_cases', Path(__file__).with_name('failure_cases.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_decomposition_separates_data_and_priors():
    document = dict(configuration=dict(scores=dict(V16=dict(common_sigma_s=3, relative_sigma_s=.15))),
                    reference_latitude_deg=38.5816, reference_longitude_deg=-121.4944, windows=100)
    row = dict(method='V16', arm='fitted-c', basin='test', calibration_penalty=7,
               fit=dict(vector=[0,0,0,0,0,0,0,3,.3,.15], objective=100,
                        signal_windows=50, posterior_rms_hz=125, converged=True,
                        boundary=False, stationarity=0, stop_reason='test'))
    d = module.decompose(row, document)
    assert d['horizontal_error_m'] < 1e-6
    assert d['common_timing_penalty'] == .5
    assert d['relative_timing_penalty'] == 2.5
    assert d['data_nll'] == 97
    assert d['selection_score'] == 107
    np.testing.assert_allclose(d['relative_timing_rms_s'], np.sqrt(.0375))
