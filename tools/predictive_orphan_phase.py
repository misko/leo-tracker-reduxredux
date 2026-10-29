"""Refresh satellite phases having no active curved calibration observations."""
import numpy as np
from scipy.linalg import cho_solve
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.predictive_track import selected_predictive_coordinates
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from prototype_dsx01_continuous_position import latlon


def attach_orphan_phase(p,entries,powers,*,orbital=False):
    active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
    orphan=sorted({e['candidate_index'] for e in entries}-active)
    p.predictive_orphan_families=orphan
    if not orphan:return p
    view,y,sigma,groups,slices=linear_geometry(p,entries)
    noise=np.diag(2*sigma*sigma)+300.**2*(groups[:,None]==groups[None,:])
    begin=p.hardware.shape[1]+p.smooth.shape[1];indices=[begin+p.labels.index(j) for j in orphan]
    orbital_slots={j:list(range(begin+len(p.labels)+3*p.supported.index(j),begin+len(p.labels)+3*p.supported.index(j)+3))
                   for j in orphan if orbital and j in p.supported}
    indices=np.array(indices+[k for slots in orbital_slots.values() for k in slots])
    base_calculate=p.calculate;base_state=p.state
    def calculate(x):
        original=base_calculate(x);c=dict(original);h=geometry_features(view,x,0.)['features']
        u=c['features'][p.keep];g=p.noise_groups[p.keep];w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        cov=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
        adjusted=selected_predictive_coordinates(c['coefficient'],cov,h,original['linear_raw_prediction_residual_hz'],noise,indices)
        delta=adjusted-c['coefficient']
        c['linear_raw_prediction_residual_hz']=original['linear_raw_prediction_residual_hz']-h@delta
        c['predictive_orphan_phase_s']={j:float(adjusted[begin+p.labels.index(j)]*p.phase_sigma[p.labels.index(j)]) for j in orphan}
        c['predictive_orphan_orbit_coordinates']={j:adjusted[slots].copy() for j,slots in orbital_slots.items()}
        c['orphan_receiver_coefficient_change']=float(np.max(abs(delta[:begin])))
        return c
    def state(x):
        result=base_state(x);result=dict(result,phases=result['phases'].copy())
        for j,phase in p.calculate(x)['predictive_orphan_phase_s'].items():result['phases'][j]=phase
        return result
    p.calculate=calculate;p.state=state
    return p


def exact_phase_replay(p,x,entries):
    c=p.calculate(x);maximum=0.
    phases=c.get('predictive_orphan_phase_s',{})
    for entry in entries:
        j=entry['candidate_index']
        if j not in phases:continue
        view,*_=linear_geometry(p,[entry]);g=geometry_features(view,x,0.)
        phase=phases[j];local=p.labels.index(j);t=p.scan.tracks[entry['track_index']]
        bank={k:p.scan.sky[k][[j]] for k in ['position_km','velocity_km_s']};bank['time_s']=p.scan.sky['time_s']
        f,_=paired_phase_frequency(bank,t['times'],np.zeros(len(t['times']),int),np.array([phase]),*latlon(x))
        linear=g['intercept']+g['derivative']*phase
        maximum=max(maximum,float(np.max(abs((f-linear)*view.q))))
    return dict(orphan_phases_s=phases,maximum_phase_linearization_error_hz=maximum,
        orphan_orbit_coordinates=c.get('predictive_orphan_orbit_coordinates',{}),
        phases_in_bounds=all(abs(v)<=15 for v in phases.values()),
        receiver_coefficient_change=c.get('orphan_receiver_coefficient_change',0.))
