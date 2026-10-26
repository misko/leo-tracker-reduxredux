"""Lean research staging for unchanged later-sample CFO and causal graph rebuild.

No donor posterior, GPS, catalogue identity or position result is an input.
Staging is exploratory; a separate RF/graph review and root approval precedes
position execution. Public persisted contracts are never modified here.
"""

import copy
import hashlib
import json
import math

from baseline_scope import native_row


class Blocked(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def upper95(k,n):
    if type(k) is not int or type(n) is not int or n<=0 or not 0<=k<=n:
        raise Blocked('valid independent null counts required')
    if k==0:
        return -math.expm1(math.log(.05)/n)
    if k==n:
        return 1.
    lo,hi=0.,1.
    for _ in range(80):
        p=(lo+hi)/2
        logs=[math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)
              +j*math.log(p)+(n-j)*math.log1p(-p) for j in range(k+1)]
        largest=max(logs)
        cdf=math.exp(largest)*sum(math.exp(x-largest) for x in logs)
        if cdf>.05:lo=p
        else:hi=p
    return hi


def screen_controls(strong_trials,null_strata):
    """Practical RF screen; no global family-wise/deployment FAR assertion."""
    if len({r['independent_target_id'] for r in strong_trials})!=len(strong_trials):
        raise Blocked('repeated strong targets cannot inflate independent trials')
    strong_n=len(strong_trials)
    accurate=sum(bool(r['admitted']) and abs(r['cfo_error_hz'])<=500 for r in strong_trials)
    catastrophes=sum(bool(r['admitted']) and abs(r['cfo_error_hz'])>1000 for r in strong_trials)
    strong_pass=strong_n>=20 and accurate/strong_n>=.9 and catastrophes==0
    covered=dict(edges=sorted({r['edge'] for r in strong_trials}),
        nonzero_evolution=any(r['true_rate_hz_s']!=0 for r in strong_trials),
        donor_error_signs=sorted({int(math.copysign(1,r['donor_error_hz'])) for r in strong_trials if r['donor_error_hz']!=0}),
        timing_error_signs=sorted({int(math.copysign(1,r['timing_error_samples'])) for r in strong_trials if r['timing_error_samples']!=0}))
    coverage_ok=covered['edges']==['lower','upper'] and covered['nonzero_evolution'] and covered['donor_error_signs']==[-1,1] and covered['timing_error_signs']==[-1,1]
    nulls={}
    for name,rows in null_strata.items():
        if len({r['independent_target_id'] for r in rows})!=len(rows):
            raise Blocked('correlated null repeats cannot inflate trial count')
        if not all(r['complete_selection_repeated'] for r in rows):
            raise Blocked('nulls omit proposal/selection exposure')
        n=len(rows);k=sum(r['confirmed'] for r in rows)
        bound=upper95(k,n)
        nulls[name]=dict(independent_trials=n,false_confirmations=k,observed_rate=k/n,
            upper95=bound,passes=n>=32 and k/n<=.05 and bound<=.10)
    passed=bool(strong_pass and coverage_ok and nulls and all(r['passes'] for r in nulls.values()))
    return dict(schema='missed-visit-practical-screen-v1',strong_trials=strong_n,
        strong_accurate_within500=accurate,strong_admitted_errors_over1000=catastrophes,
        strong_frequency_pass=strong_pass,control_regimes=covered,regimes_pass=coverage_ok,
        nulls=nulls,exploratory_RF_screen_passed=passed,
        global_familywise_FAR_qualified=False,new_uncertainty_calibrated=False,
        promotion_authorized=False)


def validated_intervals(intervals,start,stop):
    out=[]
    for a,b in intervals:
        if type(a) is not int or type(b) is not int or not start<=a<b<=stop:
            raise Blocked('sample intervals must be exact native counters inside target')
        out.append((a,b))
    return sorted(out)


def overlap(left,right):
    """Linear scan over sorted raw support envelopes, including all guards."""
    i=j=0
    while i<len(left) and j<len(right):
        a,b=left[i];c,d=right[j]
        if max(a,c)<min(b,d):return True
        if b<=d:i+=1
        else:j+=1
    return False


def validate_support(candidate,native):
    partition=candidate['support_partition']
    if partition.get('covers_entire_proposal_bank') is not True or partition.get('includes_interpolation_guards') is not True:
        raise Blocked('support must cover every mode/timing block and interpolation guard')
    search=validated_intervals(partition['all_search_envelopes'],native['start_counter'],native['stop_counter'])
    confirm=validated_intervals(partition['confirmation_envelopes'],native['start_counter'],native['stop_counter'])
    if not search or not confirm or overlap(search,confirm):
        raise Blocked('search and confirmation raw support are not disjoint')
    if candidate['selection_sealed_utc_ns']>=candidate['confirmation_started_utc_ns']:
        raise Blocked('proposal selection was not sealed before confirmation')
    if candidate.get('confirmation_retuned') is not False:
        raise Blocked('confirmation cannot retune the selected mode/timing')
    if candidate['reference_counter']!=(native['start_counter']+native['stop_counter'])/2:
        raise Blocked('CFO reference must match native baseline midpoint')
    return dict(search_envelopes=len(search),confirmation_envelopes=len(confirm),
        support_sha256=digest(partition))


def stage_observations(document,original,candidates,screen):
    """One scalar later-sample frequency per native owner; graph review remains."""
    if candidates and not screen.get('exploratory_RF_screen_passed'):
        raise Blocked('practical RF controls do not pass')
    receivers=sorted({p['receiver_id'] for p in document['source']['probes']})
    inventory={}
    for probe in document['source']['probes']:
        r=native_row(document,probe,receivers)
        if r['observation_id'] in inventory:raise Blocked('duplicate native inventory owner')
        inventory[r['observation_id']]=r
    rows=copy.deepcopy(original);owners={r['observation_id']:i for i,r in enumerate(rows)}
    if len(owners)!=len(rows):raise Blocked('duplicate original owner')
    for row in rows:
        n=inventory[row['observation_id']]
        if any(row[k]!=n[k] for k in ('receiver','native_receiver_id','channel','actual_rf_hz','time_s')):
            raise Blocked('existing owner metadata differs from raw source')
    staged=[];seen=set()
    for candidate in candidates:
        oid=candidate['target_observation_id']
        if oid in seen or oid not in inventory:raise Blocked('unknown or duplicate target alternative')
        seen.add(oid);n=inventory[oid]
        if candidate['measurement_source']!='unchanged_later_sample_scorer':
            raise Blocked('carry or donor-conditioned posterior is not a new measurement')
        if candidate.get('uses_donor_posterior_penalty') is not False:
            raise Blocked('donor-posterior information cannot enter target likelihood')
        if candidate.get('original_target_used_for_selection') is not False:
            raise Blocked('archived oracle cannot choose an operational discovery')
        for key in ('receiver','native_receiver_id','channel','edge','actual_rf_hz','sample_rate_hz',
                    'recording_id','stream_generation','raw_authority_digest'):
            if candidate['native'][key]!=n[key]:raise Blocked('native source/RX/RF mapping drift')
        support=validate_support(candidate,n)
        confirm=candidate['confirmation']
        if not math.isfinite(confirm['cfo_hz']) or not math.isfinite(confirm['margin']) or confirm['margin']<.025:
            raise Blocked('unchanged confirmation gate did not pass')
        if candidate.get('scope')!='development':
            raise Blocked('held-validation staging requires a separately frozen root release')
        for donor in candidate['donors']:
            dn=inventory.get(donor['native_observation_id'])
            if dn is None or dn['stop_counter']>n['start_counter']:
                raise Blocked('donor must bind an earlier disjoint native owner')
            if any(dn[k]!=n[k] for k in ('receiver','native_receiver_id','channel','edge','actual_rf_hz',
                                        'sample_rate_hz','recording_id','stream_generation','raw_authority_digest')):
                raise Blocked('donor is not same native lane')
        predicted=candidate['prediction_at_reference']
        compatible=abs(confirm['cfo_hz']-predicted['cfo_hz'])<=predicted['frozen_half_width_hz']
        if candidate['association_claim']=='donor_continuation' and not compatible:
            raise Blocked('far FFT winner is target pilot support, not donor continuity')
        if candidate['association_claim'] not in ('donor_continuation','independent_pilot_discovery'):
            raise Blocked('explicit pilot-versus-continuity claim required')
        if oid in owners:
            action='correct_existing';i=owners[oid]
            if candidate.get('expected_existing_cfo_hz')!=rows[i]['measured_cfo_hz']:
                raise Blocked('correction lacks exact original measurement binding')
            row=copy.deepcopy(rows[i]);row['measured_cfo_hz']=confirm['cfo_hz'];rows[i]=row
        else:
            action='new_native_detection'
            row={k:n[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')}
            row.update(measured_cfo_hz=confirm['cfo_hz'],fractional_margin=confirm['margin'])
            rows.append(row)
        staged.append(dict(target_observation_id=oid,action=action,source_support=support,
            pilot_confirmed=True,frequency_prediction_compatible=compatible,
            association_claim=candidate['association_claim'],donors_are_conditioning=True,
            native_midpoint_counter=candidate['reference_counter'],
            actual_RF_scale=n['actual_rf_hz']/11.5e9,
            receiver_band_offset_group=2*(n['receiver']-1)+int(n['channel']>4),
            uncertainty_policy='existing baseline radio-noise proxy; exploratory, not newly calibrated',
            donor_posterior_reused=False,proposal_exposure=candidate['proposal_exposure']))
    return dict(schema='missed-visit-exploratory-observations-v1',observations=rows,
        observations_sha256=digest(rows),staged=staged,
        corrections=sum(r['action']=='correct_existing' for r in staged),
        new_native_detections=sum(r['action']=='new_native_detection' for r in staged),
        status='baseline_unchanged' if not staged else 'RF_staged_pending_fresh_causal_graph',
        old_bank_reuse_authorized=False,bank_support_audit_required=bool(staged),position_execution_authorized=False,
        qualified_promotion=False,geographic_truth_opened=False)


def graph_inputs_changed(original_rows,staged_rows,original_tracks,staged_tracks):
    changed=digest(original_rows)!=digest(staged_rows) or digest(original_tracks)!=digest(staged_tracks)
    return dict(changed=changed,bank_full_catalogue_and_time_support_audit_required=changed,
        fresh_radio_noise_and_graph_receipts_required=changed,
        existing_causal_history_requires_cutoff_and_source_validation=changed,
        prior_candidate_identity_cannot_be_forced=changed,
        old_bank_receipt_valid_for_new_inputs=not changed)


def bank_reuse_audit(bank_times,bank_norads,elements,receipt,original_tracks,new_tracks,phase_margin_s=15.):
    """Reuse a complete causal regional bank only when its support is unchanged."""
    if receipt.get('reference_position_used') is not False:
        raise Blocked('bank provenance used a geographic reference')
    if receipt.get('search_center')!=[37.906,-122.545] or receipt.get('search_box_width_km')!=25.:
        raise Blocked('bank regional search authority differs')
    if not new_tracks or not original_tracks or not bank_times:
        raise Blocked('explicit original/new track and bank time support required')
    catalogue={int(v) for v in bank_norads}
    if len(catalogue)!=len(bank_norads) or catalogue!={int(v) for v in elements}:
        raise Blocked('bank does not contain the complete declared regional catalogue')
    cutoff=receipt['cutoff_utc_ns']
    for element in elements.values():
        p=element['provenance']
        if max(p['element_epoch_utc_ns'],p['collected_utc_ns'])>cutoff:
            raise Blocked('noncausal catalogue element')
    original_duration=max(300.,max(max(t['times']) for t in original_tracks))
    new_duration=max(300.,max(max(t['times']) for t in new_tracks))
    minimum=min(min(t['times']) for t in new_tracks)-phase_margin_s
    maximum=max(max(t['times']) for t in new_tracks)+phase_margin_s
    # The original broad regional elevation filter was evaluated through this duration.
    unchanged_filter_horizon=new_duration<=original_duration
    covers=min(bank_times)<=minimum and max(bank_times)>=maximum
    return dict(reuse_allowed=bool(unchanged_filter_horizon and covers),
        complete_causal_catalogue=True,candidate_count=len(catalogue),
        original_filter_duration_s=original_duration,new_filter_duration_s=new_duration,
        original_filter_horizon_sufficient=unchanged_filter_horizon,
        phase_margin_s=phase_margin_s,required_time_range_s=[minimum,maximum],
        bank_time_range_s=[min(bank_times),max(bank_times)],time_support_sufficient=covers,
        regeneration_required=not(unchanged_filter_horizon and covers))
