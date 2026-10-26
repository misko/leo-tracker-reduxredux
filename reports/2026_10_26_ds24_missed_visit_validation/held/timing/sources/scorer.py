"""One earlier-only full-window timing point per method, no target selection."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import numpy as np

R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/timing')
FROZEN_MATH_SHA256='69fa2e2b10a2bd63f79ee955af13468f9806644a057ac2c1e94d616a8485b89b'
path=R01/'timing_search.py'
if hashlib.sha256(path.read_bytes()).hexdigest()!=FROZEN_MATH_SHA256:raise ValueError('round1 owned scorer changed')
spec=importlib.util.spec_from_file_location('sealed_round1_GLRT_math',path)
math=importlib.util.module_from_spec(spec);spec.loader.exec_module(math)

VERSION='primary-fullwindow-timing-v2'
METHODS=('linear','quadratic_or_fallback','legacy_adapter_linear')
GATE=.025
BIN_HZ=10_000_000/(44*512)


def score_packet(samples,sample_rate_hz,edge,prediction):
    """Truth-free API. Companion method scores never select an acceptance arm."""
    header=prediction['header'];support=prediction['target_support']
    if len(samples)!=support['stop_counter']-support['start_counter']:raise ValueError('native support length mismatch')
    if sample_rate_hz!=header['sample_rate_hz']:raise ValueError('native sample rate mismatch')
    owner=f"{header['source_id']}/rx{header['receiver_id']}/{support['start_counter']}:{support['stop_counter']}"
    out=dict(schema=VERSION,owner_id=owner,prediction_id=prediction['prediction_id'],
        target_support=copy.deepcopy(support),status=prediction['status'],methods={},
        primary_operational_method='quadratic_or_fallback',companion_methods_are_controls=True,
        target_timing_or_mode_search=False,uncertainty_weights_qualified=False,
        independent_added_Doppler_points=0,reference_convention='nominal midpoint-effective constant epoch relative to target origin')
    if prediction['status']=='no_donor':return out
    for donor in prediction['donors']:
        if donor['stop_counter']>support['start_counter']:raise ValueError('earlier donor overlaps target')
    out['donors']=copy.deepcopy(prediction['donors']);out['source_primary_hypothesis_id']=prediction['primary_hypothesis_id']
    cache={};score_cache={}
    for name in METHODS:
        point=prediction['methods'][name]
        key=(point['epoch_samples'],point['cfo_hz'],point['cfo_rate_hz_s'],point['reference_offset_s'])
        if key not in score_cache:
            score_cache[key]=math.scores(samples,sample_rate_hz,edge,point,[0],dict(intervals=[]),'all',cache)[0]
        score=copy.deepcopy(score_cache[key]);complete=score['status']=='complete'
        innovation=score['tracking_cfo_hz']-point['cfo_hz'] if complete else None
        pilot=bool(complete and score['margin']>=GATE)
        compatible=bool(complete and abs(innovation)<=point['cfo_half_width_hz'])
        out['methods'][name]=dict(point=copy.deepcopy(point),score=score,
            pilot_confirmed=pilot,continuity_compatible=compatible,admitted=bool(pilot and compatible),
            earlier_prediction_CFO_hz=point['cfo_hz'],frequency_innovation_hz=innovation,
            frequency_bin_spacing_hz=BIN_HZ,
            grid_origin_modulo_bin_hz=float(point['cfo_hz']%BIN_HZ),
            method_is_operational=name=='quadratic_or_fallback',full_target_support_used=True,
            timing_search_evaluations=0,frequency_posterior_used=False,
            actual_sample_weighted_reference_known=False)
    out['operational_admitted']=out['methods']['quadratic_or_fallback']['admitted']
    out['distinct_fullwindow_scores']=len(score_cache)
    return out
