"""One conservative primary timing quadratic; unchanged earlier CFO/provenance."""
import copy
import math
import numpy as np

VERSION='primary-constant-epoch-quadratic/v2'
HEADER_FIELDS=('prediction_id','request_id','case','channel','receiver_id','edge','fraction',
    'sample_rate_hz','window_samples','start_counter','stop_counter','visit_index','probe_index',
    'generation','stream_generation','source_id','actual_rf_hz','tracking_sha256','raw_recording_authority_digest')


def wrap(x,period):return (x+period/2)%period-period/2


def fit_model(header,mode):
    donors=mode['donors'];rate=header['sample_rate_hz'];last=donors[-1]
    reasons=[]
    if len(donors)<5:reasons.append('fewer_than_five_donors')
    if len({d['start_counter']for d in donors})!=len(donors):raise ValueError('duplicate donor visit')
    for donor in donors:
        if donor['stop_counter']>header['start_counter']or not 0<=donor['candidate_rank']<=8 or donor['margin']<.025:
            raise ValueError('causality or original donor rank/gate violation')
        if donor['generation']!=header['generation']:raise ValueError('native generation mismatch')
        if donor['reference_counter']!=(donor['start_counter']+donor['stop_counter'])/2:
            raise ValueError('unhandled donor reference convention')
    reference=last['reference_counter']
    times=np.array([(d['reference_counter']-reference)/rate for d in donors])
    span=float(times[-1]-times[0])
    if span<1.:reasons.append('history_span_below_one_second')
    center=float(np.mean(times));scale=span/2
    result=dict(donor_count=len(donors),history_span_s=span,reference_counter=reference,
        epoch_reference_start_counter=last['start_counter'],epoch_reference_base_samples=last['epoch_samples'],
        measurement_reference='nominal midpoint-effective constant epoch; epoch is relative to window origin',
        center_relative_reference_s=center,scale_s=scale,status='fallback',fallback_reasons=reasons)
    if len(donors)<3 or scale<=0:return result
    u=(times-center)/scale;design=np.column_stack((np.ones(len(u)),u,u*u))
    condition=float(np.linalg.cond(design));rank=int(np.linalg.matrix_rank(design))
    result.update(design_condition=condition,design_rank=rank)
    if rank!=3:reasons.append('quadratic_design_rank_not_three')
    if condition>100:reasons.append('quadratic_design_condition_above_100')
    if reasons:return result
    phase=np.array([wrap(d['epoch_samples']+(d['start_counter']-last['start_counter'])-last['epoch_samples'],rate/750)
                    for d in donors])
    beta=np.linalg.lstsq(design,phase,rcond=None)[0];residual=phase-design@beta
    acceleration=float(2*beta[2]/scale**2)
    references=[header['start_counter'],(header['start_counter']+header['stop_counter'])/2,header['stop_counter']]
    target_u=[((r-reference)/rate-center)/scale for r in references]
    target_rates=[float((beta[1]+2*beta[2]*v)/scale)for v in target_u]
    if abs(acceleration)>10:reasons.append('timing_acceleration_above_10')
    if any(abs(value)>200 for value in target_rates):reasons.append('target_timing_rate_above_200')
    # Covariance is computed only in the well-conditioned scaled design.
    _,r=np.linalg.qr(design,mode='reduced');inverse_r=np.linalg.solve(r,np.eye(3))
    variance=max(.75**2,float(residual@residual/(len(donors)-3)))
    covariance=variance*(inverse_r@inverse_r.T)
    result.update(coefficients_scaled=beta.tolist(),coefficient_covariance_scaled=covariance.tolist(),
        donor_phase_samples=phase.tolist(),donor_residual_samples=residual.tolist(),
        residual_degrees_of_freedom=len(donors)-3,measurement_variance_floor_applied_samples2=variance,
        acceleration_samples_per_s2=acceleration,
        acceleration_SE_samples_per_s2=float(2*math.sqrt(covariance[2,2])/scale**2),
        target_start_mid_end_rates_samples_per_s=target_rates,
        status='quadratic'if not reasons else'fallback')
    return result


def evaluate(model,rate,target_start_counter,reference_counter):
    t=(reference_counter-model['reference_counter'])/rate
    u=(t-model['center_relative_reference_s'])/model['scale_s']
    design=np.array([1.,u,u*u]);beta=np.array(model['coefficients_scaled'])
    phase=float(design@beta)
    epoch=(model['epoch_reference_base_samples']-(target_start_counter-model['epoch_reference_start_counter'])+phase)%(rate/750)
    covariance=np.asarray(model['coefficient_covariance_scaled'])
    latent_var=float(design@covariance@design)
    variance=model['measurement_variance_floor_applied_samples2']+latent_var+2.**2
    return dict(reference_counter=reference_counter,epoch_samples=float(epoch),
        timing_rate_samples_s=float((beta[1]+2*beta[2]*u)/model['scale_s']),
        timing_sigma_samples=float(math.sqrt(variance)),timing_half_width_samples=float(3*math.sqrt(variance)),
        uncertainty_calibrated=False,reference_is_nominal_midpoint_effective=True)


def linear_point(header,mode):
    full=mode['full'];rate=header['sample_rate_hz'];mid=(header['start_counter']+header['stop_counter'])/2
    half=(header['stop_counter']-header['start_counter'])/(2*rate);tr=full['timing_rate_samples_per_s']
    result=dict(epoch_samples=full['epoch_samples'],cfo_hz=full['CFO_hz'],
        cfo_rate_hz_s=full['CFO_rate_hz_per_s'],cfo_reference_counter=full['reference_counter'],
        reference_offset_s=(full['reference_counter']-header['start_counter'])/rate,
        cfo_half_width_hz=full['CFO_half_width_hz'],CFO_sigma_hz=full['CFO_sigma_hz'],
        timing_reference_counter=mid,timing_reference_offset_s=half,timing_rate_samples_s=tr,
        timing_sigma_samples=full['timing_sigma_samples'],timing_half_width_samples=full['timing_half_width_samples'],
        epoch_at_target_origin_samples=float((full['epoch_samples']-tr*half)%(rate/750)),
        epoch_at_target_end_samples=float((full['epoch_samples']+tr*half)%(rate/750)),
        constant_epoch_approximation=True,maximum_within_window_timing_approximation_samples=abs(tr)*half,
        measurement_reference='nominal midpoint-effective historical constant epoch',uncertainty_calibrated=False)
    return result


def predict(row):
    header={k:copy.deepcopy(row['header'][k])for k in HEADER_FIELDS if k in row['header']};rate=header['sample_rate_hz']
    out=dict(schema=VERSION,header=header,target_support=copy.deepcopy(row.get('target_support')),
        prediction_id=header['prediction_id'],status='no_donor',methods={},primary_hypothesis_id=None,donors=[],
        target_outcomes_used=False,branch_selection_unchanged=True,CFO_unchanged=True,
        new_independent_observations=0)
    forecast=row.get('forecast',{})
    if not forecast.get('modes'):return out
    if forecast.get('primary_mode')!=0:raise ValueError('unexpected frozen primary mode')
    mode=forecast['modes'][0]
    linear=linear_point(header,mode);legacy=copy.deepcopy(linear)
    midpoint_offset=(header['stop_counter']-header['start_counter'])/(2*rate)
    shift=mode['full']['timing_rate_samples_per_s']*midpoint_offset
    legacy['epoch_samples']=float((linear['epoch_samples']+shift)%(rate/750))
    legacy['interpretation']='exact round1 timing-adapter linear epoch; possible extra midpoint advance'
    model=fit_model(header,mode);quadratic=copy.deepcopy(linear)
    if model['status']=='quadratic':
        refs=[header['start_counter'],(header['start_counter']+header['stop_counter'])/2,header['stop_counter']]
        values=[evaluate(model,rate,header['start_counter'],reference)for reference in refs]
        quadratic.update(values[1]);quadratic['timing_reference_counter']=values[1]['reference_counter']
        quadratic['epoch_at_target_origin_samples']=values[0]['epoch_samples']
        quadratic['epoch_at_target_end_samples']=values[2]['epoch_samples']
        quadratic['origin_mid_end_model_evaluations']=values
        quadratic['maximum_within_window_timing_approximation_samples']=max(abs(wrap(v['epoch_samples']-values[1]['epoch_samples'],rate/750))for v in values)
    out.update(status='quadratic'if model['status']=='quadratic'else'linear_fallback',
        source_primary_status=mode['status'],primary_hypothesis_id=mode['hypothesis_id'],
        donors=copy.deepcopy(mode['donors']),model=model,
        legacy_adapter_minus_consistent_linear_epoch_samples=float(wrap(legacy['epoch_samples']-linear['epoch_samples'],rate/750)),
        methods=dict(linear=linear,quadratic_or_fallback=quadratic,legacy_adapter_linear=legacy))
    return out
