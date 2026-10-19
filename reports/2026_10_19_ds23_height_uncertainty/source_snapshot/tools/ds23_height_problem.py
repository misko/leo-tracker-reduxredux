"""One marginalized antenna height, with full physical-geometry relinearization.

Height priors are fixed engineering hypotheses, not a surveyed site altitude.
No GPS, catalogue selection, recording access or point selection occurs here.
"""

import numpy as np

from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import absolute_phase_linearization
from probe_ds23_receiver_smooth_prior import scale_posterior
from probe_ds23_refined_precision import precision_problem
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def geometry_features(p, position, altitude_m):
    """Same three physical modes and absolute-phase design as JointMarginal."""
    if not np.isfinite(altitude_m) or p.variant=='empirical':
        raise ValueError('finite altitude and fixed physical prior scales required')
    coordinates=latlon(np.asarray(position)[:2])
    def frequency(phase):
        return paired_phase_frequency(p.sky,p.flat_times,p.flat_labels,phase,*coordinates,altitude_m=altitude_m)
    f,elevation=frequency(p.reference)
    derivative=(frequency(p.reference+.01)[0]-frequency(p.reference-.01)[0])/.02
    intercept=absolute_phase_linearization(f,derivative,p.reference[p.flat_labels])
    phase=np.zeros((len(f),len(p.labels)))
    phase[np.arange(len(f)),p.flat_labels]=p.q*derivative*p.phase_sigma[p.flat_labels]
    modes=paired_frequency_modes(p.sky,p.mode_bank,p.flat_times,p.flat_labels,p.reference,*coordinates,altitude_m=altitude_m)
    orbital=np.zeros((len(f),3*len(p.supported)))
    for k,j in enumerate(p.supported_local):
        use=p.flat_labels==j
        orbital[use,3*k:3*k+3]=p.q[use,None]*modes[use]
    hardware=p.hardware.copy();hardware[:,[4,6]]*=10
    features=np.column_stack((hardware,p.smooth*200,phase,orbital,p.constants))
    return dict(features=features,elevation=elevation,scales=np.ones(3),frequency=f,
                intercept=intercept,derivative=derivative)


def height_column(p, position, reference_height_m, orbital_coefficient, step_m=50.):
    """Differentiate current physical mean, including existing orbit correction."""
    if step_m<=0 or not np.isfinite(step_m):raise ValueError('positive finite height difference step required')
    begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    stop=begin+3*len(p.supported)
    coefficient=np.asarray(orbital_coefficient)
    if coefficient.shape!=(stop-begin,):raise ValueError('one coefficient per existing physical orbit mode required')
    values=[]
    for altitude in (reference_height_m+step_m,reference_height_m-step_m):
        geometry=geometry_features(p,position,altitude)
        values.append(p.q*geometry['frequency']+geometry['features'][:,begin:stop]@coefficient)
    return (values[0]-values[1])/(2*step_m)


def make_height_problem(scan,node,keep,arm,reference,powers,means,model,noise,
                        height_sigma_m,reference_height_m=0.,orbital_coefficient=None):
    if not np.isfinite([height_sigma_m,reference_height_m]).all() or height_sigma_m<0:
        raise ValueError('nonnegative finite height SD and finite reference height required')
    if height_sigma_m==0 and reference_height_m!=0:raise ValueError('zero-height control must relinearize at zero')
    p=precision_problem(scan,node,keep,arm,reference,powers,means,model,noise)
    start=p.hardware.shape[1]+p.smooth.shape[1]
    height_index=start+len(p.labels)+3*len(p.supported)
    width=height_index+1+len(p.members)
    orbital=np.zeros(3*len(p.supported)) if orbital_coefficient is None else np.asarray(orbital_coefficient)
    mean=np.zeros(width);mean[start:start+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[start:start+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(position):
        geometry=geometry_features(p,position,reference_height_m)
        d=(np.zeros(len(p.values)) if height_sigma_m==0 else
           height_column(p,position,reference_height_m,orbital))
        features=np.column_stack((geometry['features'][:,:height_index],d*height_sigma_m,
                                  geometry['features'][:,height_index:]))
        intercept=geometry['intercept']-d*reference_height_m/p.q
        raw=p.values-p.q*intercept-features@mean
        present=np.unique(p.noise_groups[keep])
        result=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        result=scale_posterior(result,scale)
        result['latent_coefficient']=result['coefficient'].copy();result['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=result['noise_precision'];result['noise_precision']=precision
        result['conditional_residual_hz']=p.values-p.q*intercept-features@result['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep])))
        result['residual']=np.r_[result['residual'],np.sqrt(volume)]
        geometry.update(result,features=features,intercept=intercept,height_derivative_hz_m=d,
            height_posterior_mean_m=float(height_sigma_m*result['coefficient'][height_index]))
        return geometry
    p.calculate=calculate
    p.height_index=height_index;p.height_sigma_m=height_sigma_m;p.height_reference_m=reference_height_m
    p.height_orbit_start=start+len(p.labels)
    return p


def exact_height_replay(p,position):
    c=p.calculate(position);height=c['height_posterior_mean_m']
    coefficient=np.delete(c['coefficient'],p.height_index)
    exact=geometry_features(p,position,height)
    exact_mean=p.q*exact['intercept']+exact['features']@coefficient
    approximate=p.q*c['intercept']+c['features']@c['coefficient']
    error=exact_mean-approximate
    return dict(height_m=height,maximum_CFO_difference_hz=float(max(abs(error[p.keep]))),
        RMS_CFO_difference_hz=float(np.sqrt(np.mean(error[p.keep]**2))),
        maximum_difference_in_point_noise_units=float(max(abs(error[p.keep])/p.point_noise[p.keep])),
        height_reference_difference_m=float(height-p.height_reference_m))


def height_uncertainty(p,position,powers):
    """Local covariance with Gamma precisions fixed, including horizontal position."""
    c=p.calculate(position);coefficient=c['coefficient'];columns=[]
    for k in (0,1):
        delta=np.zeros(2);delta[k]=.01;values=[]
        for x in (np.asarray(position)+delta,np.asarray(position)-delta):
            d=p.calculate(x);values.append(p.q*d['intercept']+d['features']@coefficient)
        columns.append((values[0]-values[1])/.02)
    features=np.column_stack((*columns,c['features']))
    w=powers[p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
    gram=np.diag(np.r_[np.zeros(2),c['coefficient_prior_precision']])+features[p.keep].T@(features[p.keep]*w[:,None])
    root=np.linalg.cholesky((gram+gram.T)/2);inverse=np.linalg.solve(root,np.eye(len(root)));covariance=inverse.T@inverse
    index=2+p.height_index
    height_sd=p.height_sigma_m*np.sqrt(covariance[index,index])
    correlation=covariance[:2,index]/np.sqrt(np.diag(covariance)[:2]*covariance[index,index])
    return dict(local_height_sigma_m=float(height_sd),height_east_north_correlation=correlation,
                local_horizontal_covariance_km2=covariance[:2,:2],
                conditional_on_Gamma_precisions_and_discrete_identities=True)
