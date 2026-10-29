"""Marginalized frequency change events for controlled ALGO02 experiments.

Existing orbit, receiver and fragment coordinates retain their original slots.
New Gaussian event coordinates are appended. Predictive linear measurements
carry their event/calibration covariance but never update calibration.
"""

import copy
import numpy as np

from ds23_predictive_linear import linear_geometry, predictive_residual
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def event_design(times, receivers, channels, rf_hz, labels, events):
    t,rx,ch,rf,j=np.broadcast_arrays(np.asarray(times,float),np.asarray(receivers),
        np.asarray(channels),np.asarray(rf_hz,float),np.asarray(labels))
    if t.ndim!=1 or not all(np.isfinite(v).all() for v in (t,rx,ch,rf,j)):
        raise ValueError('matching finite one-dimensional event coordinates required')
    columns=[]
    for event in events:
        if event['kind'] not in ('receiver','receiver_RF','band','family'):
            raise ValueError('unknown event kind')
        if not np.isfinite(event['time_s']) or not np.isfinite(event['sigma_hz']) or event['sigma_hz']<0:
            raise ValueError('finite event time and nonnegative prior SD required')
        transition=float(event.get('transition_s',0.))
        if not np.isfinite(transition) or transition<0:
            raise ValueError('finite nonnegative event transition required')
        use=(t>=event['time_s']).astype(float) if transition==0 else np.clip((t-event['time_s'])/transition,0.,1.)
        if event['kind']=='family':use*=j==event['candidate_index']
        else:use*=rx==event['receiver']
        if event['kind']=='band':use*=(ch>4)==bool(event['band'])
        if event['kind'] in ('receiver_RF','family'):use*=rf/11.5e9
        columns.append(use*event['sigma_hz'])
    return np.column_stack(columns) if columns else np.zeros((len(t),0))


def track_events(track,label,events):
    n=len(track['times'])
    return event_design(track['times'],np.full(n,track['receiver']),np.full(n,track['channel']),
                        np.full(n,track['rf_hz']),np.full(n,label),events)


def make_event_problem(scan,node,keep,arm,reference,powers,means,model,events,*,base_problem_factory=None):
    factory=make_problem if base_problem_factory is None else base_problem_factory
    p=factory(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.events=list(events)
    labels=np.asarray(p.labels)[p.flat_labels]
    receivers=np.concatenate([np.full(len(scan.tracks[i]['times']),scan.tracks[i]['receiver']) for i in p.members])
    channels=np.concatenate([np.full(len(scan.tracks[i]['times']),scan.tracks[i]['channel']) for i in p.members])
    design=event_design(p.flat_times,receivers,channels,p.q*11.5e9,labels,events)
    original_calculate=p.calculate;original_state=p.state;original_frequency=p.conditional_frequency
    original_width=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members)
    p.event_start=original_width
    if not events:return p
    width=original_width+len(events);begin=p.hardware.shape[1]+p.smooth.shape[1]
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scales=np.ones(width);scales[original_width-len(p.members):original_width]=.3
    def calculate(position):
        geometry=JointMarginal.calculate(p,position)
        features=np.column_stack((geometry['features'],design))
        raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=np.asarray(powers)[present],prior_groups=None if model['nu'] is None else groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        bound=scale_posterior(bound,scales)
        bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound,features=features,event_amplitudes_hz=np.array([e['sigma_hz'] for e in events])*
                        bound['coefficient'][original_width:])
        return geometry
    p.calculate=calculate
    radio=[k for k,e in enumerate(events) if e['kind']!='family']
    family=[k for k,e in enumerate(events) if e['kind']=='family']
    p.scan=copy.copy(scan)
    base_hardware=scan.hardware;nb=8+int(arm=='fitted_c')
    def hardware(track,beta):
        base=base_hardware(track,np.asarray(beta)[:nb])
        if radio:
            # beta stores physical Hz amplitudes, so use unit prior scales here.
            unit=[dict(events[k],sigma_hz=1.) for k in radio]
            base=base+track_events(track,-1,unit)@np.asarray(beta)[nb:]
        return base
    p.scan.hardware=hardware
    def state(position):
        result=original_state(position);c=p.calculate(position)
        amplitudes=c['event_amplitudes_hz'];result['frequency_events_hz']=amplitudes
        if radio:result['beta']=np.r_[result['beta'],amplitudes[radio]]
        return result
    p.state=state
    def conditional_frequency(position):
        f,elevation=original_frequency(position)
        if family:
            c=p.calculate(position)
            f=f+design[:,family]@c['coefficient'][original_width+np.asarray(family)]/p.q
        return f,elevation
    p.conditional_frequency=conditional_frequency
    return p


def attach_event_predictive(p,entries,powers):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    rx=np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']),p.scan.tracks[e['track_index']]['receiver']) for e in entries])
    ch=np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']),p.scan.tracks[e['track_index']]['channel']) for e in entries])
    labels=np.asarray(p.labels)[view.flat_labels]
    design=event_design(view.flat_times,rx,ch,view.q*11.5e9,labels,p.events)
    curved=p.calculate
    def calculate(position):
        c=curved(position);g=p.noise_groups[p.keep]
        weights=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        features=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+features.T@(features*weights[:,None])
        geometry=geometry_features(view,position,0.)
        all_features=np.column_stack((geometry['features'],design))
        predicted=view.q*geometry['intercept']+all_features@c['coefficient']
        prediction=predictive_residual(values-predicted,all_features,gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['objective'];c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_slices=slices;p.linear_entries=entries
    return p


def event_profile(raw,design,sigma,groups,prior_sigma_hz=300.):
    """Exact conditional Gaussian bound, eliminating one constant per curve."""
    y,d,s,g=np.asarray(raw,float),np.asarray(design,float),np.asarray(sigma,float),np.asarray(groups,int)
    if y.ndim!=1 or d.ndim!=2 or d.shape[0]!=len(y) or s.shape!=y.shape or g.shape!=y.shape or np.any(s<=0):
        raise ValueError('matching event measurements, positive noise and curve groups required')
    constants=np.eye(int(g.max())+1)[g]*prior_sigma_hz
    u=np.column_stack((d,constants))/s[:,None];z=y/s
    normal=np.eye(u.shape[1])+u.T@u;rhs=u.T@z;coefficient=np.linalg.solve(normal,rhs)
    cost=float(z@z-rhs@coefficient+np.linalg.slogdet(normal)[1])
    return dict(cost=cost,coefficient=coefficient,covariance=np.linalg.inv(normal))


def extend_event_associations(p,x,metrics):
    """Same full-graph extension gates, including candidate-specific family events."""
    from evaluate_ds23_phase_refreshed import extend_associations
    if not any(e['kind']=='family' for e in p.events):return extend_associations(p,x,metrics)
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
    from leo.analysis.research.retained_track_likelihood import profile
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from prototype_dsx01_continuous_position import latlon
    scan,state=p.scan,p.state(x);c=p.calculate(x)
    accepted={r['component']:dict(r,association_source='curved_calibration') for r in metrics['tracks'] if r['compatible']}
    labels=sorted({r['candidate_index'] for r in accepted.values()})
    supported={(scan.tracks[i]['receiver'],int(scan.tracks[i]['channel']>4)) for i in p.members
               if scan.tracks[i]['key'] in accepted}
    predictions=[];elevations=[];available=[]
    begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    for j in labels:
        phase=np.array([state['phases'][j]])
        if abs(phase[0])>15:continue
        bank=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][[j]],velocity_km_s=scan.sky['velocity_km_s'][[j]])
        f,e=paired_phase_frequency(bank,scan.times,np.zeros(len(scan.times),int),phase,*latlon(x))
        if j in p.supported:
            k=p.supported.index(j);local=p.labels.index(j)
            modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],
                       velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
            derivative=paired_frequency_modes(bank,modes,scan.times,np.zeros(len(scan.times),int),phase,*latlon(x))
            f+=derivative@c['coefficient'][begin+3*k:begin+3*k+3]
        for event,amplitude in zip(p.events,c['event_amplitudes_hz'],strict=True):
            if event['kind']=='family' and event['candidate_index']==j:
                f+=(scan.times>=event['time_s'])*amplitude
        predictions.append(f);elevations.append(e);available.append(j)
    frequencies,elevations=np.asarray(predictions),np.asarray(elevations)
    for i,t in enumerate(scan.tracks):
        if t['key'] in accepted or not available or (t['receiver'],int(t['channel']>4)) not in supported:continue
        q=t['rf_hz']/11.5e9;ix=scan.index[i]
        y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
        terms=profile(y,q*frequencies[:,ix],*scan.white[i]);noise=batch_noise_screen(terms['innovations'],t['times'])
        good=(terms['rms']<=450)&(abs(terms['bias'])<=3000)&noise['noise_screen_pass']&(elevations[:,ix].min(axis=1)>=0)
        if not good.any():continue
        k=int(np.argmin(np.where(good,terms['cost'],np.inf)));j=available[k]
        accepted[t['key']]=dict(component=t['key'],candidate_index=j,norad=int(scan.norads[j]),points=len(y),
            compatible=True,native_rms_hz=float(terms['rms'][k]),bias_hz=float(terms['bias'][k]),
            association_source='frozen_calibration_extension',active_curvature=i in scan.curved)
    return dict(tracks=list(accepted.values()),accepted_points=sum(r['points'] for r in accepted.values()),
                accepted_tracks=len(accepted))
