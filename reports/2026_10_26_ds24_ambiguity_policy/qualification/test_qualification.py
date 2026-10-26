import copy
import numpy as np
from adequacy import mode_mean,source_gate
from qualify import witness_choice,sr

def test_mode_mean_matches_augmented_dense_solution():
    rng=np.random.default_rng(2026102602);B=rng.normal(size=(19,3));raw=rng.normal(size=19);C=np.eye(19)+np.ones((19,19))*.3
    z=mode_mean(raw,C,B);expected=B.T@np.linalg.solve(C+B@B.T,raw)
    np.testing.assert_allclose(z,expected,atol=1e-12,rtol=1e-12)

def test_one_alias_applied_before_residual_gate():
    from leo.analysis.research.retained_track_likelihood import PERIOD
    n=20;t=np.arange(n,dtype=float);raw=10*np.sin(t);white=(np.eye(n)/150.,0.)
    a=source_gate(raw,t,white,np.ones(n));b=source_gate(raw+PERIOD,t,white,np.ones(n))
    assert a['residual_alias']==0 and b['residual_alias']==-1
    np.testing.assert_allclose(a['rms_hz'],b['rms_hz'],atol=1e-8)
    assert b['primitive']['alias'] is False

def test_witness_metadata_selection_ignores_candidate_values():
    d=dict(case='c',component='d',receiver=1,channel=1,rf_hz=10.,start_s=0.,end_s=10.,span_s=10.,points=12,observation_ids=['d'],eligible=True,exclusion_reasons=[])
    a=dict(d,component='a',receiver=2,observation_ids=['a'],candidate_norad=1)
    b=dict(d,component='b',channel=2,observation_ids=['b'],candidate_norad=2)
    rows=[a,b];first=witness_choice(rows,d);rows=copy.deepcopy(rows);rows[0]['candidate_norad']=99999;rows[1]['candidate_norad']=1
    assert first==witness_choice(rows,d) and first['selected']['component']=='a'

def test_original_screen_schema_to_phase_MAP_without_optional_phase_key():
    from types import SimpleNamespace as S
    from scipy.stats import t
    from adequacy import phase_map
    n=12;times=np.arange(n);frequency=np.arange(9)[:,None]*np.linspace(1,2,n)[None]
    cat=dict(frequency_hz=frequency,derivative_hz_per_s=np.ones((9,n)),phase_sd_s=np.ones(9),minimum_mean_elevation_deg=np.ones(9),norads=np.arange(1,10))
    screen=sr.previous.ordinary_screen(dict(raw_hz=np.zeros(n),covariance_hz2=np.eye(n)),cat)
    assert len(screen['candidate_indices'])==8 and 'coarse_absolute_phase_s' not in screen
    def geometry(cd,x,phases):
        return dict(frequency_hz=np.asarray(phases)[:,None]*np.linspace(30,50,n)[None],shape_columns_hz=np.zeros((len(phases),n,3)),elevation_deg=np.ones((len(phases),n)))
    fake=S(law=lambda d:dict(distribution=t(3,loc=.2,scale=.2),mass=float(t(3,loc=.2,scale=.2).cdf(15)-t(3,loc=.2,scale=.2).cdf(-15)),location=.2,sd=.2*np.sqrt(3)),k=S(m=S(q=S(phase_geometry=geometry))),sm=sr.sm)
    aliases=np.arange(-4,5)[:,None];comp=dict(x=np.zeros(2),raw=.15*np.linspace(30,50,n),q=np.ones(n),covariance=np.eye(n),aliases=aliases,shifts=aliases*np.ones((1,n))/4.4e-6)
    result=phase_map({},comp,fake,np.nan)
    assert abs(result['phase_s']-.15)<.001 and result['alias']==0
