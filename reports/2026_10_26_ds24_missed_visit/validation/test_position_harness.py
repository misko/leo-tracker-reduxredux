"""Owned tests for fair fresh-input staging and process-local read guard."""
import copy

from position_run import BIN,floored_noise
from position_harness.position_read_audit import forbidden


def test_full_bin_floor_preserves_every_incumbent_effective_scale():
    proxy=dict(extra_parameter_BIC_gain=7.,constant_radio_sigma_hz=100.,
        per_observation_noise_sigma_hz={'old':80.,'new':90.})
    before=copy.deepcopy(proxy);out=floored_noise(proxy,['old','new'],{'new'})
    assert proxy==before
    assert out['per_observation_noise_sigma_hz']=={'old':80.,'new':BIN}
    assert out['extra_parameter_BIC_gain_is_activation_sentinel']
    assert out['measured_extra_parameter_BIC_gain']==7.
    assert 'not a measured BIC gain' in out['research_override']


def test_constant_proxy_is_materialized_before_override():
    proxy=dict(extra_parameter_BIC_gain=-2.,constant_radio_sigma_hz=110.,
        per_observation_noise_sigma_hz={'old':70.,'new':60.})
    out=floored_noise(proxy,['old','new'],{'new'})
    assert out['per_observation_noise_sigma_hz']=={'old':110.,'new':BIN}


def test_inference_read_guard_allows_own_inputs_and_rejects_truth_and_old_results(tmp_path):
    root=tmp_path/'run'
    assert not forbidden(root/'case/bank.npz',root)
    assert not forbidden('/srv/bulk/leo/research/ds25-20261024/engine/ds24_engine.py',root)
    assert forbidden('/srv/bulk/leo/research/ds25-20261024/DS24-0011/result.json',root)
    assert forbidden(root/'gps.json',root)
    assert forbidden('/home/mouse9911/gits/leo-tracker-reduxredux/reports/old/endpoints.json',root)
    assert not forbidden('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json',root)
    assert not forbidden('/tmp/algo03-feasible-deps/scipy-1.18.1.dist-info/entry_points.txt',root)
