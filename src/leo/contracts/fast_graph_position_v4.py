"""ALGO05: separate persisted major for paired conditional gap recovery."""
import math
from leo.contracts.fast_graph_position import ARMS, KIND
from leo.contracts.fast_graph_position_v3 import validate_terminal as validate_v3, published_owners

MODEL_VERSION='algo05-causal-gap-conditional-v1'
NAMESPACE='fast-scan-graph-position-v4'

def incumbent_proof(terminal):
    return terminal['candidate'] if terminal['decision']=='ALGO04_additive' else terminal['incumbent']

def owners(terminal):
    proof=incumbent_proof(terminal)
    return {a:published_owners(proof,a) for a in ARMS}

def qualify(trial,audit,incumbent,universe):
    reasons=[]
    if not trial.get('paired_valid'):reasons.append('paired RF gates fail')
    if audit is None or not audit.get('all_verified'):reasons.append('exact replay fails or missing')
    if set(trial.get('arms',{}))!=set(ARMS):
        return dict(qualified=False,reasons=reasons+['missing matched c arm'])
    additions={}
    for arm in ARMS:
        row=trial['arms'][arm];new=row.get('proposed_owners',{})
        ids=set(row.get('proposed_associated_ids',[]))
        if set(new)!=ids:reasons.append(arm+': owner and point sets differ')
        if not ids<=universe:reasons.append(arm+': unknown observations')
        if any(new.get(i)!=n for i,n in incumbent[arm].items()):reasons.append(arm+': incumbent owners not preserved')
        phase=row.get('final_phase_change_s',float('inf'))
        if not isinstance(phase,(float,int)) or not math.isfinite(phase) or phase<0 or phase>.01:
            reasons.append(arm+': phase not converged')
        additions[arm]={i:n for i,n in new.items() if i not in incumbent[arm]}
    if additions['c0']!=additions['fitted_c']:reasons.append('c-arm additions differ')
    return dict(qualified=not reasons,reasons=reasons,added_points={a:len(v) for a,v in additions.items()})

def validate_terminal(doc,*,input_sha256):
    try:return _validate(doc,input_sha256)
    except (KeyError,TypeError,IndexError,OverflowError) as e:raise ValueError('Malformed v4 terminal') from e

def _validate(d,sha):
    if (d.get('schema_version')!=4 or d.get('kind')!=KIND or d.get('model_version')!=MODEL_VERSION
        or d.get('input_sha256')!=sha or d.get('state') not in ('complete','failed','unavailable')):
        raise ValueError('Graph position v4 identity mismatch')
    if d['state']!='complete':
        if d.get('position') is not None:raise ValueError('Unqualified position')
        return d
    old=validate_v3(d['incumbent'],input_sha256=sha)
    if old['state']!='complete' or old['session_id']!=d['session_id']:raise ValueError('Wrong ALGO04 incumbent')
    if (d.get('reference_usage')!='none' or d.get('future_TLE_used') is not False
        or d.get('matched_c_inputs') is not True or d.get('selected_arm')!='fitted_c'):
        raise ValueError('Contradictory inference provenance')
    times=[d[k] for k in ('incumbent_seconds','recovery_seconds','total_seconds')]
    if (any(not isinstance(t,(int,float)) or isinstance(t,bool) or not math.isfinite(t) or t<0 for t in times)
        or times[0]!=old['total_seconds'] or times[1]>1200 or times[2]>4800
        or abs(times[0]+times[1]-times[2])>1e-6):raise ValueError('Invalid runtime accounting')
    if d['decision']=='ALGO04_fallback':
        if d['position']!=old['position']:raise ValueError('Fallback must preserve exact ALGO04 position')
        return d
    if d['decision']!='ALGO05_additive':raise ValueError('Unknown v4 decision')
    c=d['candidate']
    if (c['policy']!='gap_conditional' or c['identity']['status']!='conditionally_supported_identity'
        or (d.get('read_audit') or {}).get('verified') is not True
        or (incumbent_proof(old).get('read_audit') or {}).get('verified') is not True):
        raise ValueError('Missing guarded causal gap proof')
    q=qualify(c['trial'],c['audit'],owners(old),set(c['observation_ids']))
    if not q['qualified'] or q['added_points']['fitted_c']<=0:raise ValueError('Unqualified paired recovery: '+str(q['reasons']))
    target=c['target_ids'];parent=c['parent_ids'];times=c['target_times_s']
    if (len(target)<12 or len(set(target))!=len(target) or not set(target)<set(parent)
        or len(times)!=len(target) or not all(math.isfinite(t) for t in times)
        or times[-1]-times[0]<10 or any(not 0<b-a<=5 for a,b in zip(times,times[1:]))):
        raise ValueError('Invalid proper timing-gap fragment')
    for arm in ARMS:
        if set(target)&set(owners(old)[arm]) or any(c['trial']['arms'][arm]['proposed_owners'].get(i)!=c['identity']['norad'] for i in target):
            raise ValueError('Target ownership inconsistent with independent nomination')
    exact=c['audit']['rows']
    if {(r['role'],r['arm']) for r in exact}!={(role,a) for role in ('control','target_0') for a in ARMS}:
        raise ValueError('Missing exact audit arms')
    for row in exact:
        if row['verified'] is not True or not row['gate_slacks'] or any(not math.isfinite(v) or v<0 for v in row['gate_slacks'].values()):
            raise ValueError('Exact gates failed')
    for arm in ARMS:
        values=c['trial']['arms'][arm]['proposed_owners']
        if any(not isinstance(k,str) or not k or not isinstance(v,int) or isinstance(v,bool) or v<=0 for k,v in values.items()):raise ValueError('Invalid owner')
        lat,lon=c['trial']['arms'][arm]['endpoint_latlon']
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Invalid position')
    expected=dict(zip(('latitude_deg','longitude_deg'),c['trial']['arms']['fitted_c']['endpoint_latlon']))
    if d['position']!=expected:raise ValueError('Position differs from selected fit')
    return d
