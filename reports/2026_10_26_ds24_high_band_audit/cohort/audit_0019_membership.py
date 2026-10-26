"""Trace saved DS24-0019 early-family mask changes, without any replay or fit."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOTS={'all_channels':Path('/srv/bulk/leo/research/ds25-20261024'),
       'ch1_4':Path('/srv/bulk/leo/research/ds24-channel-halves-20261024/ch1_4'),
       'ch5_8':Path('/srv/bulk/leo/research/ds24-channel-halves-20261024/ch5_8')}
CASE='DS24-0019'
TARGETS={48323,57371}
SOURCES={}

def read(p):
    raw=p.read_bytes();SOURCES[str(p)]=hashlib.sha256(raw).hexdigest()
    return json.loads(raw)

def masks(node,mask,tracks):
    at=0;out={}
    for row in node['seed']['rows']:
        t=tracks[row['component']];n=len(t['times']);local=mask[at:at+n];at+=n
        assert n==row['points'] and len(local)==n
        out[row['component']]=[oid for oid,keep in zip(t['observation_ids'],local,strict=True) if keep]
    assert at==len(mask)
    return out

def labels(arm):
    out={}
    for g in arm['gates']['tracks']+arm['linear_gates']:
        if not g['compatible']: continue
        for oid in g['observation_ids']:
            assert oid not in out
            out[oid]=g['norad']
    return out

def evaluation_error_km(point):
    # The established report coordinate enters only post-hoc evaluation.
    reference=(37.849061591561885,-122.48574968092912)
    a,b=map(math.radians,point);c,d=map(math.radians,reference)
    h=math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2
    return 12742*math.asin(math.sqrt(h))

def main():
    data={};rows=[]
    for group,root in ROOTS.items():
        saved=read(root/'family_cavity/position'/(CASE+'.json'))
        original=read(root/CASE/'result.json')
        algo=read(root/CASE/'algo02_result.json')
        tracks={t['key']:t for t in read(root/CASE/'tracks.json')}
        raw=read(root/CASE/'observations.json')
        final=masks(saved['baseline_node'],saved['original_mask'],tracks)
        initial=masks(original['final_node'],original['final_mask'],tracks)
        assert sum(map(len,final.values()))==sum(algo['mask'])
        data[group]=dict(saved=saved,original=original,algo=algo,tracks=tracks,raw={o['observation_id']:o for o in raw},labels={arm:labels(a) for arm,a in saved['policy_arms'].items()})
        for row in saved['baseline_node']['seed']['rows']:
            if row['candidate_norad'] not in TARGETS:continue
            comp=row['component'];t=tracks[comp]
            removed=[e['epoch'] for e in algo['curved_gate_history'] if comp in e['failed']]
            gates={arm:[g for g in a['gates']['tracks'] if g['component']==comp] for arm,a in saved['policy_arms'].items()}
            rows.append(dict(group=group,norad=row['candidate_norad'],component=comp,receiver=t['receiver'],channel=t['channel'],times_span_s=[min(t['times']),max(t['times'])],graph_points=row['points'],initial_result_mask_points=len(initial[comp]),saved_final_mask_points=len(final[comp]),ALGO02_history_gate_removal_epochs=removed,original_seed_compatible=row['compatible'],original_seed_feasible_candidates=row['feasible_candidates'],original_seed_profile_RMS_hz=row['rms_hz'],original_seed_profile_bias_hz=row['bias_hz'],final_gates=gates))
    agreement=[]
    high=data['ch5_8'];full=data['all_channels']
    for arm in ['c0','fitted_c']:
        for target in sorted(TARGETS):
            ids={oid for oid,n in high['labels'][arm].items() if n==target}
            assert ids<=set(full['raw'])
            assert all(high['raw'][oid]==full['raw'][oid] for oid in ids)
            agreement.append(dict(arm=arm,high_model_norad=target,high_likelihood_points=len(ids),full_likelihood_label_counts=dict(Counter(str(full['labels'][arm].get(oid,'UNASSOCIATED')) for oid in ids))))
    saved=high['saved'];trial_excerpts=[];derived=[]
    for i,t in enumerate(saved['trials']):
        # These values are copied exactly from the named source JSON paths.
        exact={k:t[k] for k in ['replacements','paired_valid','constrained_refinement_attempted']}
        exact['arms']={arm:{k:a[k] for k in ['endpoint_east_north_km','endpoint_latlon','negative_twice_elbo','corrected_selection_loss','RMS_hz','active_points','final_phase_change_s']} for arm,a in t['arms'].items()}
        trial_excerpts.append(dict(source_JSON_pointer='/trials/'+str(i),exact_field_excerpt=exact))
        derived.append(dict(trial_index=i,arms={arm:dict(evaluation_error_km=evaluation_error_km(a['endpoint_latlon']),negative_twice_elbo_minus_baseline=a['negative_twice_elbo']-saved['baseline_arms'][arm]['negative_twice_elbo']) for arm,a in t['arms'].items()}))
    alternatives=dict(source=str(ROOTS['ch5_8']/'family_cavity/position'/(CASE+'.json')),source_sha256=SOURCES[str(ROOTS['ch5_8']/'family_cavity/position'/(CASE+'.json'))],exact_root_field_excerpt={k:saved[k] for k in ['case','accepted','baseline_corrected_loss','search_penalty','selection_gain','adoption']},trials=trial_excerpts,derived_evaluation_only=derived,reference_coordinate_evaluation_only=[37.849061591561885,-122.48574968092912],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),interpretation='The valid 48323→67338 alternative was explicitly tested, with a worse c0 selection loss by3.8460711732695927. Its smaller evaluation error is not admissible evidence for selecting it.57371-only and combined alternatives failed paired validity.')
    (OUT/'0019_saved_alternatives_excerpt.json').write_text(json.dumps(alternatives,indent=2)+'\n')
    out=dict(case=CASE,targets=sorted(TARGETS),rows=rows,exact_observation_ID_audit=agreement,history={g:d['algo']['curved_gate_history'] for g,d in data.items()},limits=['Historical seed compatible/feasible fields remain unchanged through later recovery. Actual masks and final gates determine active membership.','Saved removal history names rejected components but retains no per-statistic failed diagnostics at the removed stage. Specific rejection causes cannot be reconstructed from final surviving gates alone.','No new fitting, geometry or IQ. No true emitter-identity assertion.'],source_files_sha256=SOURCES,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'0019_membership_history.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(agreement,indent=2))

if __name__=='__main__':main()
