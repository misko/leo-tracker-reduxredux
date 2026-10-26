"""Post-seal mapping/scales comparison to explain membership sensitivity."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from evaluate_position import read,write,likelihood_mapping,effective_scales,identity_signature,recovery
from integrate import sha
from leo.analysis.research.retained_track_likelihood import PERIOD


def native_mapping(d,arm):
    result=likelihood_mapping(d,arm);observations={o['observation_id']:o for o in d['observations']}
    for entry in d['entries']:
        track=d['scan'].tracks[entry['track_index']]
        for oid,value in zip(track['observation_ids'],track['values'],strict=True):
            result[oid]['alias_lift']=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(entry['alias'])
    return result


def main():
    assert read(HERE/'position_inference_audit.json')['all_complete']
    p=read(HERE/'position_protocol.json');rows=[];evaluation=read(HERE/'position_evaluation.json')
    for case in p['cases']:
        controls=next(c for c in p['controls'] if c['case']==case);roots={'baseline':Path(controls['root'])}
        roots.update({j['variant']:Path(j['root']) for j in p['jobs'] if j['case']==case})
        mappings={};scales={}
        for variant,root in roots.items():
            recovery.SOURCE=root;d=recovery.context(case);mappings[variant]=native_mapping(d,'c0');scales[variant]=effective_scales(root,case)
        base=mappings['baseline'];proxy=mappings['additions_proxy'];floor=mappings['additions_bin_floor'];old=set(scales['baseline'])
        changed=[]
        for oid in sorted(set(base)&set(proxy)):
            a,b=identity_signature(base[oid]),identity_signature(proxy[oid])
            if a!=b:changed.append(dict(observation_id=oid,before=a,after=b,
                changes=[k for k in a if a[k]!=b[k]]))
        assert all(scales['additions_proxy'][oid]==scales['additions_bin_floor'][oid] for oid in old)
        rows.append(dict(case=case,baseline_to_proxy_changed_retained_IDs=changed,
            proxy_to_floor_likelihood_ID_sets_equal=set(proxy)==set(floor),
            proxy_to_floor_reassigned_retained_IDs=[oid for oid in set(proxy)&set(floor) if identity_signature(proxy[oid])!=identity_signature(floor[oid])],
            proxy_to_floor_incumbent_noise_scales_exactly_equal=True,
            lost_baseline_likelihood_IDs=sorted(set(base)-set(proxy)),
            gained_incumbent_likelihood_IDs=sorted((set(proxy)-set(base))&old)))
        for attribution in evaluation['attribution']:
            if attribution['case']!=case:continue
            for identity in attribution['new_likelihood_identities']:
                identity['membership']['alias_lift']=mappings[attribution['variant']][identity['observation_id']]['alias_lift']
                identity['membership']['alias_coordinate']='total native CFO lift including graph and predictive-entry aliases'
    write(HERE/'position_association_changes.json',dict(cases=rows,new_fits=0,new_RF_reads=0,
        interpretation='Baseline-to-additions changes fresh associations and reestimates incumbent noise; proxy-to-floor holds all incumbent scales fixed. No additional counterfactual sweep was run.'))
    evaluation.update(original_evaluation_sha256=sha(HERE/'position_evaluation.json'),
        reporting_alias_normalization='Predictive entry alias is relative to graph-lifted values; include graph lift to report total native CFO alias. Position/frequency metrics and all memberships unchanged.',
        normalized_alias_source_sha256=sha(__file__))
    write(HERE/'position_evaluation_native.json',evaluation)
    print([{k:(len(v) if isinstance(v,list) else v) for k,v in row.items()} for row in rows])


if __name__=='__main__':main()
