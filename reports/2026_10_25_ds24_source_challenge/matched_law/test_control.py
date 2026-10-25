import numpy as np
from law_math import gaussian_score,gaussian_qr_score,near_null,pair_choice,draw


def test_gaussian_density_and_alias_normalization():
    rng=np.random.default_rng(32);n=9;b=rng.normal(size=(n,4))*2;c=np.diag(np.arange(1,n+1.))
    y=rng.normal(size=n);m=rng.normal(size=n)
    a,_=gaussian_score(y,c,m,b)
    assert abs(a-gaussian_qr_score(y,c,m,b))<1e-9
    assert abs(a-gaussian_score(y+3,c,m+3,b)[0])<1e-9


def test_null_projection_and_response_free_pair():
    times=np.linspace(0,20,11);f=np.array([times,times+1,times+30]);d=np.ones_like(f)
    choice,_=pair_choice(f,d,np.ones(3),np.eye(11),[0,1,2],np.array([9,7,12]))
    assert set(choice[3:])=={0,1}
    mean,factor,q,cov,floor=near_null(times,f[:2],d[:2],[2.,3.],[np.ones((11,3)),np.ones((11,3))*2],np.ones(11)*4)
    assert np.allclose(q.T@q,np.eye(5))
    assert np.linalg.eigvalsh(cov).min()>0
    assert np.isclose(floor*5,11*16)
    assert np.allclose(factor@factor.T,q@cov@q.T)


def test_draw_reproducibility_and_complete_forward_identity():
    mean=np.arange(7.);factor=np.eye(7)[:,:3];c=np.eye(7)*2
    values,record=draw(mean,c,mean*3,factor,51,2)
    again,_=draw(mean,c,mean*3,factor,51,2)
    assert np.array_equal(values,again)
    assert np.allclose(values+record['alias']/4.4e-6,mean*4+factor@record['latent_z']+record['noise_Hz'])


def test_screen_equivalent_and_has_no_truth_port():
    from control import ordinary_screen,old
    times=np.arange(8.);frequency=np.array([times*3,times*4+30,times*5-10])
    catalogue=dict(frequency_hz=frequency,derivative_hz_per_s=np.ones_like(frequency)*2,
        phase_sd_s=np.ones(3),phase_means_s=np.zeros(3),minimum_mean_elevation_deg=np.ones(3),norads=np.array([5,3,8]))
    observation=dict(raw_hz=times*4+20,covariance_hz2=np.eye(8)*16)
    actual=ordinary_screen(observation,catalogue);original=old.ordinary_screen(observation,catalogue)
    assert actual['candidate_indices']==original['candidate_indices']
    assert actual['coarse_scores']==original['coarse_scores']
    try:ordinary_screen(dict(observation,truth=5),catalogue)
    except ValueError:pass
    else:raise AssertionError('truth was allowed into ordinary nomination')


def test_actual_null_generation_wrapper_c0_only():
    from control import generate
    n=7;data=dict(c0_radio_mean_Hz=np.arange(n,dtype=float),c0_covariance_Hz2=np.eye(n)*4,
        null_mean_Hz=np.arange(n,dtype=float)*2,null_factor_Hz=np.eye(n)[:,:5],
        fitted_c_radio_mean_Hz=np.zeros(n),fitted_c_covariance_Hz2=np.eye(n))
    values,truth=generate(None,data,dict(case='DS24-0010'),2)
    changed=dict(data,fitted_c_radio_mean_Hz=np.ones(n)*1e6,fitted_c_covariance_Hz2=np.eye(n)*900)
    again,_=generate(None,changed,dict(case='DS24-0010'),2)
    assert np.array_equal(values,again)
    assert truth['kind']=='near_null' and truth['candidate_index'] is None


def test_actual_physical_generation_wrapper(monkeypatch):
    import control
    n=7;data=dict(c0_radio_mean_Hz=np.arange(n,dtype=float),c0_covariance_Hz2=np.eye(n)*4,
        norads=np.array([80,90]),q=np.ones(n)*1.1,position_east_north_km=np.zeros(2))
    monkeypatch.setattr(control.k,'candidate',lambda *args:dict(target=dict(phase_nu=3,phase_sd_s=2.,phase_mean_s=.2)))
    monkeypatch.setattr(control.k.m.q,'phase_geometry',lambda *args:dict(
        frequency_hz=np.ones((1,n))*7,shape_columns_hz=np.ones((1,n,3)),elevation_deg=np.ones((1,n))*45))
    values,truth=control.generate({},data,dict(case='DS24-0010',pair_indices=[0,1]),0)
    assert truth['norad']==80 and -15<truth['phase_s']<15
    expected=data['c0_radio_mean_Hz']+truth['physical_or_null_mean_Hz']+truth['physical_or_null_factor_Hz']@truth['latent_z']+truth['noise_Hz']-truth['alias']*control.lm.PERIOD
    assert np.allclose(values,expected)
