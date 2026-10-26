"""Research-only observation staging. Never edits a public persisted contract.

This is a prerequisite checker, not a position solver or a source of RF approval.
Only a separately reviewed, hash-bound RF receipt can admit a proposed scalar
target likelihood. Donor-conditioned posteriors require a joint model which this
lean adapter deliberately does not implement.
"""

import copy
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'ch58-position-readiness-v1'
GATES = ('measurement_accuracy', 'uncertainty_calibration', 'natural_target_support',
         'multiplicity_and_nulls', 'ownership_and_dependence')
MATCHED_FIELDS = ('observations_sha256', 'candidate_catalog_sha256', 'alias_map_sha256',
                  'physical_priors_sha256', 'search_budget', 'region_center',
                  'box_width_km', 'start_east_north_km', 'causal_catalog_receipt_sha256')


class Blocked(ValueError):
    """A required RF or integration prerequisite is absent or inconsistent."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def null_upper(false_confirmations, independent_trials, alpha=.05):
    """One-sided exact Clopper-Pearson bound; trials must be independent groups."""
    k,n=false_confirmations,independent_trials
    if type(k) is not int or type(n) is not int or not 0<=k<=n or n<=0 or not 0<alpha<1:
        raise Blocked('explicit valid independent-null trial accounting required')
    if k==n:
        return 1.
    if k==0:
        return -math.expm1(math.log(alpha)/n)
    low,high=0.,1.
    for _ in range(80):
        p=(low+high)/2
        terms=[math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)
               +j*math.log(p)+(n-j)*math.log1p(-p) for j in range(k+1)]
        largest=max(terms)
        cdf=math.exp(largest)*sum(math.exp(t-largest) for t in terms)
        if cdf>alpha:
            low=p
        else:
            high=p
    return high


def validate_nulls(receipt):
    """Bonferroni uses full exposure, never a count of selected positive cells."""
    if receipt.get('conditional_on_same_donor_state') is not True:
        raise Blocked('conditional donor-matched nulls missing')
    if receipt.get('same_full_proposal_search') is not True:
        raise Blocked('nulls do not repeat the complete proposal search')
    exposure=receipt.get('family_exposure')
    if type(exposure) is not int or exposure<1:
        raise Blocked('full family exposure missing')
    if receipt.get('independent_grouping_documented') is not True:
        raise Blocked('correlated null replicates cannot be counted independently')
    upper=null_upper(receipt['false_confirmations'],receipt['independent_trials'])
    family_bound=min(1.,exposure*upper)
    if family_bound>.05:
        raise Blocked(f'95% null upper bound cannot certify family FPR <=.05: {family_bound:.6g}')
    return dict(per_search_upper_95=upper,family_upper_95=family_bound,exposure=exposure)


def validate_rf_receipt(receipt, protocol_sha256):
    if receipt.get('protocol_sha256')!=protocol_sha256:
        raise Blocked('qualification protocol digest differs')
    if receipt.get('independent_review') is not True:
        raise Blocked('independent RF review absent')
    if any(receipt.get('gates',{}).get(g)!='pass' for g in GATES):
        raise Blocked('all independent RF gates must pass')
    if receipt.get('development_only') is not True:
        raise Blocked('exposed four-scan outcomes cannot claim location transfer')
    artifacts=receipt.get('evidence_artifacts',{})
    if not artifacts:
        raise Blocked('RF evidence artifact hashes absent')
    for path,sha in artifacts.items():
        if not Path(path).is_file() or file_sha(path)!=sha:
            raise Blocked('qualification evidence artifact missing or changed')
    return validate_nulls(receipt['null_exposure'])


def support_checked(support):
    required=('recording_id','stream_generation','raw_authority_digest','native_receiver_id',
              'receiver','channel','edge','start_counter','end_counter','sample_rate_hz','actual_rf_hz')
    if not all(k in support for k in required):
        raise Blocked('incomplete raw native support')
    if any(type(support[k]) is not int for k in ('start_counter','end_counter')):
        raise Blocked('native counters require exact integers')
    if not 0<=support['start_counter']<support['end_counter']:
        raise Blocked('invalid native support interval')
    if support['receiver'] not in (1,2) or support['channel'] not in range(1,9):
        raise Blocked('invalid receiver/channel mapping')
    if support['edge'] not in ('lower','upper'):
        raise Blocked('explicit native pilot edge required')
    if not all(math.isfinite(support[k]) and support[k]>0 for k in ('sample_rate_hz','actual_rf_hz')):
        raise Blocked('positive actual RF and native sample rate required')
    if not all(support[k] for k in ('recording_id','stream_generation','raw_authority_digest')):
        raise Blocked('raw source identity absent')
    return support


def same_stream(a,b):
    # Different candidate edge/channel/RF labels never make shared IQ independent.
    return all(a[k]==b[k] for k in ('recording_id','stream_generation',
                                   'raw_authority_digest','native_receiver_id'))


def overlaps(a,b):
    return same_stream(a,b) and max(a['start_counter'],b['start_counter'])<min(a['end_counter'],b['end_counter'])


def within(a,b):
    return same_stream(a,b) and b['start_counter']<=a['start_counter']<a['end_counter']<=b['end_counter']


def same_lane(a,b):
    return same_stream(a,b) and all(a[k]==b[k] for k in
        ('receiver','channel','edge','actual_rf_hz','sample_rate_hz'))


def stage(existing_observations, native_inventory, proposals, rf_receipt,
          protocol_sha256, baseline_receipt_sha256):
    """Stage one row per native target; unchanged/no-proposal input replays exactly.

    Output is an in-memory research envelope, never a replacement public contract.
    Even accepted RF rows still need causal graph/alias/support re-qualification.
    """
    existing=copy.deepcopy(existing_observations)
    original={o['observation_id']:o for o in existing}
    inventory={r['observation_id']:r for r in native_inventory}
    if len(original)!=len(existing) or len(inventory)!=len(native_inventory):
        raise Blocked('duplicate baseline/native target identity')
    if not set(original)<=set(inventory):
        raise Blocked('baseline owner lacks raw support binding')
    all_support=sorted((support_checked(row['support']) for row in native_inventory),
        key=lambda s:(str(s['recording_id']),str(s['stream_generation']),
                      str(s['raw_authority_digest']),str(s['native_receiver_id']),s['start_counter']))
    for a,b in zip(all_support,all_support[1:]):
        if overlaps(a,b):
            raise Blocked('native inventory overlaps independently owned raw support')
    for oid,row in original.items():
        inv=inventory[oid];support=inv['support']
        if any(row[k]!=support[k] for k in ('receiver','native_receiver_id','channel','actual_rf_hz')) or row['time_s']!=inv['time_s']:
            raise Blocked('baseline metadata differs from native source mapping')
    nulls=None
    if proposals:
        nulls=validate_rf_receipt(rf_receipt,protocol_sha256)
        if rf_receipt.get('baseline_receipt_sha256')!=baseline_receipt_sha256:
            raise Blocked('RF review bound to another baseline')
    owners=set()
    changes=[]
    for proposal in proposals:
        oid=proposal['target_observation_id']
        if oid not in inventory or oid in owners:
            raise Blocked('unknown or duplicate target/mode ownership')
        owners.add(oid)
        inv=inventory[oid];owner=inv['support']
        target=support_checked(proposal['measurement_support'])
        if not within(target,owner) or not same_lane(target,owner):
            raise Blocked('target sample identity, RF or receiver mapping differs')
        if proposal.get('proposal_digest') not in rf_receipt.get('qualified_proposal_digests',[]):
            raise Blocked('proposal was not individually reviewed')
        content={k:v for k,v in proposal.items() if k!='proposal_digest'}
        if digest(content)!=proposal['proposal_digest']:
            raise Blocked('proposal changed after RF review')
        if proposal.get('measurement_kind')!='target_only_likelihood':
            raise Blocked('donor-conditioned posterior cannot become an independent likelihood; joint covariance required')
        if proposal.get('uncertainty_kind')!='calibrated_target_likelihood_sd_hz':
            raise Blocked('margin/mode score is not calibrated target likelihood uncertainty')
        if proposal.get('mode_count')!=1:
            raise Blocked('multiple same-target modes need an alternative likelihood model')
        if proposal.get('full_scan_track_prediction_used') is not False:
            raise Blocked('causal earlier-only donor certification missing')
        for donor in proposal.get('donors',[]):
            ds=support_checked(donor['support'])
            did=donor['observation_id']
            if did not in inventory or inventory[did]['support']!=ds:
                raise Blocked('donor not bound to exact native source inventory')
            if not same_lane(ds,target) or ds['end_counter']>target['start_counter'] or overlaps(ds,target):
                raise Blocked('donor overlaps target or is not earlier same lane')
            if donor.get('role')!='conditioning_only':
                raise Blocked('donor carry is not a second measurement')
        cfo,sigma=proposal['measured_cfo_hz'],proposal['sigma_hz']
        if not math.isfinite(cfo) or not math.isfinite(sigma) or sigma<=0:
            raise Blocked('finite measured CFO and positive calibrated uncertainty required')
        kind=proposal['kind']
        if kind=='correct_existing':
            if oid not in original or proposal.get('expected_existing_cfo_hz')!=original[oid]['measured_cfo_hz']:
                raise Blocked('correction lacks exact existing measurement authority')
            row=copy.deepcopy(original[oid]);row['measured_cfo_hz']=cfo
            # Keep the exact original owner/metadata and all other baseline fields.
            existing[next(i for i,o in enumerate(existing) if o['observation_id']==oid)]=row
        elif kind=='new_native_detection':
            if oid in original or inv.get('existing_winner') is not False:
                raise Blocked('new detection already has a native baseline owner')
            row=dict(observation_id=oid,receiver=owner['receiver'],
                native_receiver_id=owner['native_receiver_id'],channel=owner['channel'],
                time_s=inv['time_s'],measured_cfo_hz=cfo,actual_rf_hz=owner['actual_rf_hz'])
            existing.append(row)
        else:
            raise Blocked('only corrections and genuinely new native targets may stage')
        changes.append(dict(target_observation_id=oid,kind=kind,sigma_hz=sigma,
            measurement_support=target,proposal_digest=proposal['proposal_digest'],
            raw_cfo_hz=cfo,actual_rf_scale=owner['actual_rf_hz']/11.5e9,
            calibration_group=2*(owner['receiver']-1)+int(owner['channel']>4),
            alias_policy='preserve existing lifts for correction; causal graph must validate all admissions',
            likelihood_source='later native samples only',
            donor_ids=[d['observation_id'] for d in proposal.get('donors',[])]))
    if len({o['observation_id'] for o in existing})!=len(existing):
        raise Blocked('staging duplicated native observation owners')
    return dict(schema=SCHEMA,status='baseline_unchanged' if not changes else 'RF_staged_pending_causal_graph_review',
        baseline_receipt_sha256=baseline_receipt_sha256,protocol_sha256=protocol_sha256,
        observations=existing,observations_sha256=digest(existing),changes=changes,
        corrected_existing=sum(c['kind']=='correct_existing' for c in changes),
        new_native_detections=sum(c['kind']=='new_native_detection' for c in changes),
        null_bounds=nulls,position_execution_authorized=False,
        primary_dependency_approval_required=bool(changes),
        geographic_evaluation_permitted=False)


def validate_position_pair(c0,fitted_c):
    """A future execution receipt must pin matched c arms and causal catalogues."""
    if c0.get('arm')!='c0' or fitted_c.get('arm')!='fitted_c':
        raise Blocked('explicit c0/fitted_c paired arms required')
    for field in MATCHED_FIELDS:
        if field not in c0 or field not in fitted_c or c0[field]!=fitted_c[field]:
            raise Blocked('unmatched c-arm '+field)
    for arm in (c0,fitted_c):
        if arm['region_center']!=[37.906,-122.545] or arm['box_width_km']!=25. or arm['start_east_north_km']!=[0.,0.]:
            raise Blocked('regional starts differ from original authority')
        if arm.get('GPS_used') is not False or arm.get('post_scan_TLE_used') is not False:
            raise Blocked('GPS-free inference and causal TLE certificate required')
        if arm.get('causal_graph_review_passed') is not True:
            raise Blocked('RF-only admission does not establish graph association')
        if arm.get('primary_execution_approval') is not True:
            raise Blocked('primary dependency execution approval absent')
    return True
