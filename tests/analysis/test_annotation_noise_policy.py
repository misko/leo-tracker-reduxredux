from types import SimpleNamespace
import numpy as np
from include_predictive_annotations import annotation_noise_context


def test_annotation_policy_isolated_and_applies_to_calibration_and_prediction():
    scan=SimpleNamespace(fixed_window_noise={'extra_parameter_BIC_gain':10.,'per_observation_noise_sigma_hz':{'x':42.}},radio_sigma_hz=50.)
    p=SimpleNamespace(values=np.zeros(3),point_noise=np.array([40.,50.,60.]))
    source=dict(scan=scan,powers=np.array([.3,.7]),problem_factory=lambda *a,**kw:p)
    changed=annotation_noise_context(source)
    assert changed['scan'] is not scan
    assert scan.radio_sigma_hz==50. and scan.fixed_window_noise['extra_parameter_BIC_gain']==10.
    np.testing.assert_array_equal(source['powers'],[.3,.7])
    np.testing.assert_array_equal(changed['powers'],[1.,1.])
    assert changed['scan'].radio_sigma_hz==150. and changed['scan'].fixed_window_noise['extra_parameter_BIC_gain']==0.
    np.testing.assert_array_equal(changed['problem_factory']().point_noise,[150.,150.,150.])
