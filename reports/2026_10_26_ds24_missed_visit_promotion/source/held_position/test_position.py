"""Component-owned checks for the frozen promotion comparison."""
import copy
import pytest
from position import floored_noise,BIN,VARIANTS,CASES,job_env
from position_read_audit import forbidden

@pytest.mark.parametrize('gain',[7.,-2.])
def test_floor_preserves_incumbents_and_proxy(gain):
    proxy=dict(extra_parameter_BIC_gain=gain,constant_radio_sigma_hz=110.,per_observation_noise_sigma_hz={'old':70.,'new':60.})
    before=copy.deepcopy(proxy);out=floored_noise(proxy,['old','new'],{'new'})
    assert proxy==before
    assert out['per_observation_noise_sigma_hz']=={'old':70. if gain>0 else 110.,'new':BIN}

def test_exact_frozen_panel_and_environment(tmp_path):
    assert len(CASES)==12 and len(set(CASES))==12
    assert VARIANTS==('baseline','additions_bin_floor','additions_proxy')
    env=job_env(tmp_path)
    assert env['OPENBLAS_NUM_THREADS']==env['OMP_NUM_THREADS']==env['MKL_NUM_THREADS']=='1'
    assert '/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src:/tmp/algo03-feasible-deps' in env['PYTHONPATH']

def test_read_guard_blocks_archived_geography_and_outcomes(tmp_path):
    assert forbidden(tmp_path/'gps.json',tmp_path)
    assert forbidden('/srv/bulk/leo/research/old/result.json',tmp_path)
    assert not forbidden(tmp_path/'case/bank.npz',tmp_path)
