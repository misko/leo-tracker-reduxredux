"""Owned finite Gaussian, normalized-allocation and mode-guard controls."""
from pathlib import Path
from unittest.mock import patch
import time
import numpy as np
import pytest
from scipy.special import logsumexp
import coherence as c


def base_model():
    rng=np.random.default_rng(2026102571);n=100
    features=rng.normal(size=(n,4))*.1
    covariance=np.eye(n)*4+features@features.T
    groups=np.r_[np.zeros(57,int),np.ones(43,int)]
    aliases,shifts=c.k.alias_vectors(groups,np.arange(-4,5));shifts=shifts/c.k.PERIOD*17.
    root=np.linalg.cholesky(covariance)
    return dict(raw=rng.normal(size=n),covariance=covariance,q=np.linspace(.98,1.02,n),root=root,
        aliases=aliases,shifts=shifts,whitened_aliases=np.linalg.solve(root,shifts.T).T,
        base_logdet=float(np.linalg.slogdet(covariance)[1]))


def test_allocation_priors_support_and_single_whole_W_alias():
    models=c.allocations(np.linspace(236,265,43),period=17.)
    assert len(models)==11 and {row['cut'] for row in models if row['cut'] is not None}=={14,21,29}
    assert sum(.25 for _ in c.CLASSES)==1
    for family in c.CLASSES:
        assert abs(sum(np.exp(row['log_within_prior']) for row in models if row['family']==family)-1)<1e-14
    base=base_model()
    for model in models:
        comp,columns=c.model_component(base,model)
        np.testing.assert_array_equal(columns[:57],0)
        np.testing.assert_array_equal(columns[57:][model['mask']],0)
        np.testing.assert_array_equal(comp['covariance'][:57],base['covariance'][:57])
        np.testing.assert_array_equal(comp['q'][:57],base['q'][:57])
        assert comp['aliases'].shape==(81,2)
        assert np.unique(comp['shifts'][:,57:],axis=1).shape[1]==1


def test_whole_polynomial_exact_original_basis_and_physical_zero_extra():
    times=np.linspace(236,265,43);models=c.allocations(times,period=17.)
    whole=next(row for row in models if row['name']=='whole_polynomial')
    expected=np.polynomial.legendre.legvander(2*(times-times.min())/np.ptp(times)-1,4)*17/np.sqrt(6)
    np.testing.assert_array_equal(whole['poly'],expected)
    base=base_model();physical=next(row for row in models if row['name']=='whole_physical')
    comp,_=c.model_component(base,physical)
    np.testing.assert_array_equal(comp['covariance'],base['covariance'])
    np.testing.assert_array_equal(comp['q'],base['q'])


def test_vectorized_kernel_matches_original_positive_Woodbury_mixture():
    base=base_model();models=c.allocations(np.linspace(236,265,43),period=17.)
    rng=np.random.default_rng(5);frequency=rng.normal(size=(3,100));shape=rng.normal(size=(3,100,3))*.3
    geometry=lambda phases:dict(frequency_hz=frequency,shape_columns_hz=shape,elevation_deg=np.ones((3,100)))
    prior=c.sr.law(dict(target=dict(phase_nu=3.,phase_sd_s=2.,phase_mean_s=.2)))
    phases=np.array([-.3,.1,.6])
    for model in models:
        comp,_=c.model_component(base,model)
        actual=c.kernel(comp,geometry,prior,phases)
        costs=c.sr.sm.positive_costs(comp['raw'][None]-frequency*comp['q'],comp['covariance'],shape*comp['q'][None,:,None],comp['shifts'])
        expected=logsumexp(-costs/2,axis=1)-np.log(81)+prior['distribution'].logpdf(phases)-np.log(prior['mass'])
        np.testing.assert_allclose(actual,expected,atol=1e-10,rtol=0)


def test_geometry_cache_reuses_exact_nodes_without_interpolation():
    calls=[]
    def geometry(d,x,phases):
        calls.extend(phases)
        return dict(frequency_hz=np.asarray(phases)[:,None]*np.arange(4)[None],
            shape_columns_hz=np.broadcast_to(np.asarray(phases)[:,None,None],(len(phases),4,3)).copy(),
            elevation_deg=np.ones((len(phases),4)))
    with patch.object(c.k.m.q,'phase_geometry',side_effect=geometry):
        cache=c.Geometry({},np.zeros(2));first=cache(np.array([.2,.3,.2]));second=cache(np.array([.3,.4]))
    assert calls==[.2,.3,.4] and cache.propagated_nodes==3
    np.testing.assert_array_equal(first['frequency_hz'][1],second['frequency_hz'][0])


def bound_rows(best='split'):
    rows=c.allocations(np.linspace(236,265,43),period=17.)
    for row in rows:
        value=-10. if row['family']==best else -30.
        row.update(log_integral64=value,bounds=dict(resolved=True,lower_log_integral=value-.01,upper_log_integral=value+.01))
    return rows


def test_class_marginalization_is_prior_average_not_best_cut():
    rows=bound_rows()
    group=c.classes(rows,tail_upper=-100.)
    split=next(row for row in group if row['family']=='split')
    assert abs(split['window_log_evidence']+10)<1e-12
    assert sum(split['within_class_window_weights'].values())==pytest.approx(1.)
    assert c.ordering(group)['winner']=='split'
    chosen=next(row for row in rows if row['name']=='cut14_prefix')
    chosen['log_integral64']=-5.
    point=next(row for row in c.classes(rows,-100.) if row['family']=='split')['window_log_evidence']
    assert point < -5. and point==pytest.approx(logsumexp([-5]+[-10]*5)-np.log(6))


def test_unresolved_remote_mass_blocks_apparently_decisive_local_winner():
    rows=bound_rows()
    assert c.ordering(c.classes(rows,-5.))['proved'] is False
    assert c.ordering(c.classes(rows,None))['proved'] is False
    group=c.classes(rows,-100.)
    group[0]['upper_log_evidence']=float('nan')
    assert c.ordering(group)['proved'] is False


def test_native_Gaussian_ceiling_survives_shared_latent_conditioning():
    rng=np.random.default_rng(99);nd,nw=5,7
    sd=np.linspace(1.,2.,nd+nw)*np.sqrt(2)
    latent=rng.normal(size=(nd+nw,6))*3
    covariance=np.diag(sd**2)+latent@latent.T
    conditional=covariance[nd:,nd:]-covariance[nd:,:nd]@np.linalg.solve(covariance[:nd,:nd],covariance[:nd,nd:])
    assert np.linalg.eigvalsh(conditional-np.diag(sd[nd:]**2)).min()>-1e-12
    peak=-.5*(nw*np.log(2*np.pi)+np.linalg.slogdet(conditional)[1])
    ceiling=-.5*(nw*np.log(2*np.pi)+np.log(sd[nd:]**2).sum())
    assert peak<=ceiling


def test_excess_common_panels_abstain_without_dropping_cuts():
    geometry=lambda x:(_ for _ in ()).throw(AssertionError('must not evaluate'))
    result=c.local_bounds({}, {},geometry,{},np.column_stack((np.arange(513),np.arange(513)+.5)),time.monotonic()+10)
    assert result['resolved'] is False and result['panels']==513


def test_Path_output_port_and_expired_deadline():
    with patch.object(c.r,'write_new') as write:c.write(Path('c0')/'port.json',dict(test=True))
    assert write.call_args.args[0]==c.HERE/'c0/port.json'
    with pytest.raises(TimeoutError):c.sr.alarm(0.)


def test_discovery_component_is_exact_D_marginal_and_nine_alias_measure():
    base=base_model();base.update(d={},times=np.arange(100.))
    comp=c.discovery_component(base)
    np.testing.assert_array_equal(comp['raw'],base['raw'][:57])
    np.testing.assert_array_equal(comp['covariance'],base['covariance'][:57,:57])
    np.testing.assert_array_equal(comp['q'],base['q'][:57])
    assert comp['aliases'].shape==(9,1)
