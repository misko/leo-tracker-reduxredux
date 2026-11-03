import numpy as np
from native_rx_difference import models,summarize_pairs
from check_other_scans import models as original_models


def test_dense_models_replay_original():
    t=np.linspace(0,300,401);ch=np.arange(len(t))%4+1
    y=10*ch+2*t+.001*t*t+np.sin(t)*10
    a=models(t,ch,y);b=original_models(t,ch,y)
    for order in ('0','1','2'):
        for key,value in b[order].items():
            if isinstance(value,(int,float)):
                assert np.isclose(a[order][key],value,rtol=1e-10,atol=1e-8)


def test_sparse_empty_folds_do_not_crash_or_invent_coverage():
    t=np.array([10.,11.,12.,100.,101.,102.,103.]);ch=np.ones(len(t))
    result=models(t,ch,t)
    for m in result.values():
        assert m['held_count']<=len(t)
        assert len(m['held_fold_counts'])<5


def test_empty_time_bins_are_explicit():
    pairs=[dict(time_s=100+i,channel=1,rx1_minus_rx0_modulo_alias_hz=20+i,
                rx1_minus_rx0_raw_hz=20+i,epoch_difference_s=1e-8,margin0=.5,margin1=.5) for i in range(10)]
    result=summarize_pairs(pairs)
    assert result['thirty_second_bin_medians'][0]['median_rx_difference_hz'] is None
    assert result['pair_count']==10
