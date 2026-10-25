"""Append active-family physical priors; freeze calibration-support semantics."""
from types import SimpleNamespace
import numpy as np

import recovery as r
from build_dsx01_orbit_modes import build_modes
from ds23_frequency_events import make_event_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry, predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from probe_ds23_receiver_smooth_prior import scale_posterior
from probe_ds23_frequency_events import cached, summary
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon


def coordinate_spec(p,means,nu,extra_count):
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    old_width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    width=old_width+3*extra_count
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if nu is not None: groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scales=np.ones(width)
    # Original fragment constants keep their original positions after append.
    scales[old_width-len(p.members):old_width]=.3
    return dict(old_width=old_width,mean=mean,groups=groups,scales=scales,
        old_constant_indices=list(range(old_width-len(p.members),old_width)),
        old_to_new=list(range(old_width)),new_indices=list(range(old_width,width)))


def extra_columns(p,x):
    count=len(getattr(p,'extra_families',()))
    out=np.zeros((len(p.flat_times),3*count))
    if not count:return out
    mode=paired_frequency_modes(p.sky,p.extra_mode_bank,p.flat_times,p.flat_labels,p.reference,*latlon(x))
    for k,j in enumerate(p.extra_families):
        use=p.flat_labels==p.labels.index(j)
        out[use,3*k:3*k+3]=p.q[use,None]*mode[use]*p.extra_scale
    return out


def geometry(p,x):
    result=geometry_features(p,x,0.)
    result['features']=np.column_stack((result['features'],extra_columns(p,x)))
    return result


def build(d,arm,reference,method,extra_scale=1.):
    if method not in ('matched_cold_baseline','retained_uncertainty'):raise ValueError('unknown frozen method')
    if extra_scale not in (0.,1.):raise ValueError('only zero-equivalence or original physical scale allowed')
    p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model'],[])
    p.original_calibration_supported=tuple(p.supported)
    native=[row['observation_id'] for row in d['observations']]
    if len(native)!=len(set(native)):raise ValueError('duplicate original GLRT IDs')
    p.native_observation_ids=tuple(native)
    p.all_track_observation_ids=tuple(sorted({oid for t in p.scan.tracks for oid in t['observation_ids']}))
    if not set(p.all_track_observation_ids)<=set(native):raise ValueError('non-native graph IDs')
    active={row['candidate_index'] for row,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
    active|={entry['candidate_index'] for entry in d['entries']}
    if not active<=set(p.labels):raise ValueError('predictive-only family lacks an inherited label/phase slot')
    p.active_likelihood_families=tuple(sorted(active))
    p.extra_families=tuple(sorted(active-set(p.supported))) if method=='retained_uncertainty' else ()
    p.extra_scale=extra_scale
    p.extra_mode_bank,p.extra_mode_metadata=build_modes(p.scan,p.labels,list(p.extra_families),'physical')
    spec=coordinate_spec(p,np.asarray(d['means']),d['model']['nu'],len(p.extra_families))
    p.extra_start=spec['old_width'];p.coordinate_spec=spec
    if getattr(p,'clock',np.empty((0,0))).shape[1]:raise ValueError('undeclared legacy clock coordinates')
    if p.extra_families:
        def curved_calculate(x):
            result=JointMarginal.calculate(p,x)
            features=np.column_stack((result['features'],extra_columns(p,x)))
            raw=p.values-p.q*result['intercept']-features@spec['mean']
            present=np.unique(p.noise_groups[p.keep])
            bound=hierarchical_bound(raw[p.keep],(features*spec['scales'])[p.keep],p.point_noise[p.keep],
                p.noise_groups[p.keep],powers=np.asarray(d['powers'])[present],
                prior_groups=None if d['model']['nu'] is None else spec['groups'],
                prior_nu=4 if d['model']['nu'] is None else d['model']['nu'])
            bound=scale_posterior(bound,spec['scales'])
            bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=spec['mean']
            precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
            bound['conditional_residual_hz']=p.values-p.q*result['intercept']-features@bound['coefficient']
            volume=float(2*np.sum(np.asarray(d['powers'])[p.noise_groups[p.keep]]*np.log(p.point_noise[p.keep]/40)))
            bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
            result.update(bound,features=features)
            return result
        p.calculate=curved_calculate
    # The inherited conditional_frequency uses a trailing constant slice; avoid
    # it explicitly because append leaves constants in their ORIGINAL slots.
    phase_begin=p.hardware.shape[1]+p.smooth.shape[1]
    orbit_stop=phase_begin+len(p.labels)+3*len(p.original_calibration_supported)
    def frequency(x,include_extra=True):
        c=p.calculate(x)
        f=c['intercept']+c['features'][:,phase_begin:orbit_stop]@c['coefficient'][phase_begin:orbit_stop]/p.q
        if include_extra and p.extra_families:f=f+c['features'][:,p.extra_start:]@c['coefficient'][p.extra_start:]/p.q
        return f,c['elevation']
    p.conditional_frequency=lambda x:frequency(x,True)
    p.conservative_frequency=lambda x:frequency(x,False)
    original_state=p.state
    def state(x):
        result=original_state(x)
        result['prior_only_physical_nuisance_coefficients']={str(j):p.calculate(x)['coefficient'][p.extra_start+3*k:p.extra_start+3*k+3]
            for k,j in enumerate(p.extra_families)}
        result['new_modes_are_not_qualified_orbit_corrections']=True
        return result
    p.state=state
    curved=p.calculate;p.curved_calculate=curved
    if d['entries']:
        view,values,sigma,groups,slices=linear_geometry(p,d['entries'])
        def calculate(x):
            # Never mutate the curved result when attaching predictive evidence.
            c=dict(curved(x));g=p.noise_groups[p.keep]
            weights=np.asarray(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
            train=c['features'][p.keep]
            gram=np.diag(c['coefficient_prior_precision'])+train.T@(train*weights[:,None])
            geo=geometry(view,x);predicted=view.q*geo['intercept']+geo['features']@c['coefficient']
            pred=predictive_residual(values-predicted,geo['features'],gram,sigma*np.sqrt(2),groups)
            c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['linear_predictive_objective']=pred['objective']
            c['negative_twice_elbo']+=pred['objective'];c['normalization_constant']+=pred['normalization_constant']
            c['residual']=np.r_[c['residual'],pred['residual']]
            c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=geo['elevation']
            c['predictive_extra_columns']=geo['features'][:,p.extra_start:]
            c['predictive_features']=geo['features'];c['predictive_sigma_hz']=sigma*np.sqrt(2)
            return c
        p.calculate=calculate;p.linear_entries=d['entries'];p.linear_slices=slices
    else:p.linear_entries=[];p.linear_slices=[]
    cached(p)
    return p


def conservative_result(p,x):
    c=dict(p.calculate(x))
    if p.extra_families:
        coefficient=c['coefficient'][p.extra_start:]
        c['conditional_residual_hz']=c['conditional_residual_hz'].copy()+c['features'][:,p.extra_start:]@coefficient
        if p.linear_entries:
            c['linear_raw_prediction_residual_hz']=c['linear_raw_prediction_residual_hz'].copy()+c['predictive_extra_columns']@coefficient
    return c


def gate_view(p,kind='conservative'):
    if kind not in ('conservative','literal_expanded_fullmean'):raise ValueError(kind)
    view=SimpleNamespace(**vars(p))
    if kind=='conservative':
        view.supported=list(p.original_calibration_supported)
        view.calculate=lambda x:conservative_result(p,x)
        view.conditional_frequency=p.conservative_frequency
    else:
        view.supported=sorted(set(p.original_calibration_supported)|set(p.extra_families))
    # All bound methods continue to read p's original coordinate layout. Only
    # retained_metrics' owner predicate sees the view's declared support set.
    return view


def summarize(p,x,entries,kind='conservative'):
    result=summary(gate_view(p,kind),x,entries)
    c=p.calculate(x)
    result.update(likelihood_conditional_RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        gate_view=kind,original_calibration_supported=list(p.original_calibration_supported),
        prior_uncertainty_available_families=sorted(set(p.original_calibration_supported)|set(p.extra_families)),
        added_prior_only_families=list(p.extra_families),coordinate_spec=p.coordinate_spec,
        final_log_precision_change=float(c['final_log_precision_change']),
        newly_added_mode_means_omitted_from_gate_and_extension=kind=='conservative')
    return result


def fingerprint(value):
    return r.hashlib.sha256(r.json.dumps(value,default=r.encode,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def coverage(p,x,entries,saved):
    from evaluate_ds23_phase_refreshed import extend_associations
    view=gate_view(p,'conservative')
    extension=extend_associations(view,x,saved['gates'])
    lookup={t['key']:t for t in p.scan.tracks}
    explicit=[dict(entry,compatible=gate['compatible'],association_source='explicit_predictive')
        for entry,gate in zip(entries,saved['linear_gates'],strict=True)]
    explicit_ids={oid for row in explicit for oid in row['observation_ids']}
    keys={row['component'] for row in explicit};rows=[];collisions=[]
    for raw in extension['tracks']:
        if not raw['compatible'] or raw['component'] in keys:continue
        row=dict(raw,observation_ids=raw.get('observation_ids',lookup[raw['component']]['observation_ids']))
        if set(row['observation_ids'])&explicit_ids:collisions.append(row['component']);continue
        rows.append(row)
    accepted_list=[oid for row in rows+explicit if row['compatible'] for oid in row['observation_ids']]
    if len(accepted_list)!=len(set(accepted_list)):raise ValueError('duplicate accepted point ownership')
    raw_accepted=set(accepted_list)
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
        for oid,keep in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if keep]
    predictive=[oid for entry in entries for oid in entry['observation_ids']]
    if len(curved)!=len(set(curved)) or len(predictive)!=len(set(predictive)) or set(curved)&set(predictive):
        raise ValueError('duplicate likelihood ownership')
    # Match the archived reference ledger: likelihood IDs remain part of its
    # retained union even when an endpoint fails the whole-source gates. The
    # separate raw gate ledger never claims those failed sources qualified.
    accepted=raw_accepted|set(curved+predictive)
    native=set(p.native_observation_ids)
    if not accepted<=native:raise ValueError('non-native postfit IDs')
    return dict(accepted_observation_ids=sorted(accepted),associated=len(accepted),total_GLRT=len(native),
        percent=100*len(accepted)/len(native),associations=rows+explicit,
        raw_gate_accepted_observation_ids=sorted(raw_accepted),raw_gate_accepted_points=len(raw_accepted),
        curved_observation_ids=sorted(curved),predictive_observation_ids=sorted(predictive),
        postfit_only_observation_ids=sorted(accepted-set(curved+predictive)),
        curved_points=len(curved),predictive_points=len(predictive),likelihood_points=len(curved)+len(predictive),
        likelihood_percent=100*(len(curved)+len(predictive))/len(native),
        active_curved_families=sorted({row['candidate_index'] for row,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}),
        supported_families=list(p.original_calibration_supported),
        colliding_postfit_extensions_omitted=collisions,prior_only_mode_means_used_for_extensions=False)


def qualification(arms):
    from algo02_scan import pair_passes
    RF=bool(set(arms)==set(r.ARMS) and pair_passes(arms,include_linear=True))
    phase=bool(set(arms)==set(r.ARMS) and all(np.max(abs(np.asarray(row['state']['phases'])))<=15.000001
        and row['final_phase_change_s']<=.01 for row in arms.values()))
    precision=bool(set(arms)==set(r.ARMS) and all(np.isfinite(row['final_log_precision_change'])
        and row['final_log_precision_change']<=1e-5 for row in arms.values()))
    return dict(original_paired_RF_gates=RF,phase_converged_both_arms=phase,Gamma_converged_both_arms=precision,
        phase_Gamma_converged_both_arms=phase and precision,conservative_paired_valid=RF and phase and precision)
