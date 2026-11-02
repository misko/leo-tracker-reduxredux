"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import copy
import math
ARMS=('c0','fitted_c')
POLICY='causal-reassociation-unique-receiver-groups-v1'


def select(baseline, records, guards):
    """Fail closed; identity repair only, never publish a prior-only update.

    The decision consumes RF gains, qualification, ownership and predictive
    competition. Geographic errors are opaque output metadata.
    """
    eligible=[];review=[]
    for row in records:
        name=row['name'];reasons=[];guard=guards.get(name)
        if not row.get('accepted'):reasons.append('original_physical_acceptance_failed')
        if not guard or not guard.get('passed') or guard.get('model')!='receiver_offset':
            reasons.append('receiver_shared_competition_not_passed')
        elif (guard.get('unique_folds',0)<5 or guard.get('missing') or
              not math.isfinite(guard.get('minimum_margin',float('nan'))) or guard['minimum_margin']<=0):
            reasons.append('incomplete_or_nonpositive_predictive_evidence')
        gains=row.get('gains',{})
        if any(not isinstance(gains.get(a),(int,float)) or not math.isfinite(gains[a]) or gains[a]<=0 for a in ARMS):
            reasons.append('paired_RF_gain_failed')
        for a in ARMS:
            fit=row.get('pair',{}).get(a) or {}
            for key in ('qualified','all_gates_pass','phase_closed','optimizer_success','mixture_phase_interior'):
                if fit.get(key) is not True:reasons.append(a+':'+key)
            if fit.get('lost_ids_count',len(fit.get('lost_ids',[]))) or fit.get('unexpected_reassigned_ids_count',len(fit.get('unexpected_reassigned_ids',[]))):
                reasons.append(a+':native_ownership_violation')
            control=row.get('control',{}).get(a) or {}
            if not fit.get('native_ids_sha256') or fit['native_ids_sha256']!=control.get('native_ids_sha256'):
                reasons.append(a+':native_evidence_not_matched')
        review.append(dict(name=name,eligible=not reasons,reasons=reasons))
        if not reasons:eligible.append(row)
    if not eligible:
        return dict(policy=POLICY,selected=None,final=copy.deepcopy(baseline),review=review)
    best=min(eligible,key=lambda r:(-sum(r['gains'][a] for a in ARMS),r['name']))
    final={a:dict(x=best['pair'][a]['x'],error_m=best['pair'][a]['error_m'],
                  objective=best['pair'][a]['objective'],rms_hz=best['pair'][a]['rms_hz'],
                  associated=baseline[a]['associated']) for a in ARMS}
    return dict(policy=POLICY,selected=best['name'],final=final,review=review)
