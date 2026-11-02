"""Compact cached coefficient diagnostics; never an acceptance gate."""
import numpy as np


def snapshot(p,x,*,target_family,covariance=None):
    calculated=p.calculate(x);state=p.state(x)
    coefficient=np.asarray(calculated['coefficient'])
    nb,ns=p.hardware.shape[1],p.smooth.shape[1]
    phase_start=nb+ns;orbit_start=phase_start+len(p.labels)
    fragment_start=orbit_start+3*len(p.supported);event_start=fragment_start+len(p.members)
    if len(coefficient)<event_start or len(coefficient)-event_start!=len(getattr(p,'events',[])):
        raise ValueError('Coefficient vector differs from declared block layout')
    layout=dict(hardware=[0,nb],smooth=[nb,phase_start],phase=[phase_start,orbit_start],
                orbit=[orbit_start,fragment_start],fragment=[fragment_start,event_start],appended_events=[event_start,len(coefficient)],
                nb=nb,ns=ns,phase_labels=list(map(int,p.labels)),
                phase_norads=[int(p.scan.norads[j]) for j in p.labels],
                orbit_supported_labels=list(map(int,p.supported)),
                orbit_supported_norads=[int(p.scan.norads[j]) for j in p.supported],orbit_width_per_family=3,
                fragment_members=list(map(int,p.members)),fragment_components=[r['component'] for r in p.rows])
    target=None
    for k,j in enumerate(p.supported):
        if int(p.scan.norads[j])!=target_family:continue
        scales=np.array([p.mode_metadata[j][name] for name in
            ('mean_motion_sigma_rev_day','inclination_sigma_deg','raan_sigma_deg')])
        transformed=coefficient[orbit_start+3*k:orbit_start+3*k+3]
        root=np.eye(3) if covariance is None else np.linalg.cholesky(np.asarray(covariance))
        original=root@transformed
        target=dict(norad=target_family,coefficient_slice=[orbit_start+3*k,orbit_start+3*k+3],
                    fitted_standardized_coefficient=transformed,original_standardized_coefficient=original,
                    transform_to_original=root,current_declared_physical_SD=scales,
                    physical_parameter_revision=scales*original,physical_units=['rev/day','deg','deg'])
    return dict(status='available',coefficient=coefficient,
        latent_coefficient=calculated.get('latent_coefficient'),
        coefficient_prior_precision=calculated.get('coefficient_prior_precision'),
        noise_precision=calculated.get('noise_precision'),phase_sigma_s=np.asarray(p.phase_sigma),
        layout=layout,orbit_mode_metadata={str(int(p.scan.norads[j])):p.mode_metadata[j] for j in p.supported},
        state=dict(beta=state['beta'],phases_for_labels_s=np.asarray(state['phases'])[p.labels],smooth=state['smooth']),
        target_orbit=target,has_shared_satellite_refresh=hasattr(p,'shared_satellite_families'),
        shared_satellite_allowed_coordinates=calculated.get('shared_satellite_allowed_coordinates'),
        objective_kind=calculated.get('objective_kind','base curved hierarchical fit with conditional predictive attachments'),
        scope='Conditional base coefficient representation, including declared shared-satellite conditional refresh when present; ancillary phase-mixture families are separately scored and are not a joint nuisance posterior',
        acceptance_gate=False)


def optional_snapshot(p,x,**kwargs):
    try:return snapshot(p,x,**kwargs)
    except Exception as exc:return dict(status='unavailable',reason=repr(exc),acceptance_gate=False)
