"""Post-terminal endpoint replay, owner/family attribution, then GPS reporting."""
import json
import math
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import recovery
from leo.analysis.research.retained_track_likelihood import PERIOD


def likelihood_mapping(d,arm):
    p=recovery.build(d,arm,d['arms'][arm]['phase_reference']);observations={o['observation_id']:o for o in d['observations']};out={}
    for row,index,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=p.scan.tracks[index]
        for oid,value,active in zip(track['observation_ids'],track['values'],p.keep[sl],strict=True):
            if not active:continue
            lift=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(alias)
            assert oid not in out
            out[oid]=dict(role='curved',norad=int(p.scan.norads[row['candidate_index']]),alias_lift=lift,graph_key=track['key'])
    for entry in d['entries']:
        for oid in entry['observation_ids']:
            assert oid not in out
            out[oid]=dict(role='predictive',norad=int(p.scan.norads[entry['candidate_index']]),alias_lift=int(entry.get('alias',0)))
    return out


def effective_scales(root,case):
    noise=read(root/case/'radio_noise.json')
    return {o['observation_id']:noise['per_observation_noise_sigma_hz'][o['observation_id']] if noise['extra_parameter_BIC_gain']>0 else noise['constant_radio_sigma_hz'] for o in read(root/case/'observations.json')}


def identity_signature(value):return {k:value[k] for k in ('role','norad','alias_lift')}


def audit():
    terminal=read(HERE/'position_final_terminal_seal.json');protocol=read(HERE/'position_protocol.json')
    assert terminal['all_terminal'] and terminal['evaluation_now_permitted'] and not terminal['denied_reads']
    assert terminal['original_protocol_sha256']==sha(HERE/'position_protocol.json') and not terminal['GPS_error_evaluation_performed']
    assert terminal['inputs_and_first_attempt_artifacts_unchanged']
    continuation=read(HERE/'engine_continuation_protocol.json')
    assert terminal['continuation_protocol_sha256']==sha(HERE/'engine_continuation_protocol.json')
    for path,h in continuation['protected_existing_files'].items():assert sha(path)==h,path
    for path,h in terminal['terminal_output_hashes'].items():assert sha(path)==h,path
    for path,h in dict(protocol['input_hashes'],**protocol['source_hashes']).items():assert sha(path)==h,path
    # Reused baseline control outputs enter reporting only after new terminal seals.
    for control in protocol['controls']:
        for path,h in control['terminal_output_hashes'].items():assert sha(path)==h,path
    jobs=sorted(protocol['jobs']+[dict(c,variant='baseline') for c in protocol['controls']],key=lambda j:(j['case'],j['variant']))
    rows=[];memberships={};mappings={};scales={};data={}
    for job in jobs:
        root=Path(job['root']);case=job['case'];variant=job['variant']
        execution=read(root/('execution.json' if variant=='baseline' else 'engine_continuation_execution.json'))
        receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
        assert len(receipts)>=3 and not any(r['denied_paths'] for r in receipts)
        reads=sorted({p for r in receipts for p in r['read_paths']})
        assert not any('gps' in Path(p).name.lower() or 'oracle' in Path(p).name.lower() for p in reads)
        row=dict(case=case,variant=variant,status=execution['status'],seconds=execution['seconds'] if variant=='baseline' else execution['total_numerical_seconds'],
            reused_control=variant=='baseline',read_receipt_processes=len(receipts),read_paths=reads)
        if execution['status']=='complete':
            recovery.SOURCE=root;d=recovery.context(case)
            members={arm:recovery.membership(d,arm,d['arms'][arm]) for arm in ('c0','fitted_c')}
            maps={arm:likelihood_mapping(d,arm) for arm in ('c0','fitted_c')}
            assert maps['c0']==maps['fitted_c']
            for k in ('curved_observation_ids','predictive_observation_ids'):
                assert members['c0'][k]==members['fitted_c'][k]
            added=set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
            row['arms']={arm:dict(objective_replay_difference=m['objective_replay_difference'],
                likelihood_points=m['likelihood_points'],curved_points=m['curved_points'],predictive_points=m['predictive_points'],
                added_curved_ids=sorted(added&set(m['curved_observation_ids'])),
                added_predictive_ids=sorted(added&set(m['predictive_observation_ids'])),
                added_accepted_ids=sorted(added&set(m['accepted_observation_ids'])),
                accepted_GLRT_count=m['associated'],total_GLRT_count=m['total_GLRT'],
                associated_GLRT_fraction=m['associated']/m['total_GLRT'],
                original_GLRT_count=m['total_GLRT']-len(added),native_added_count=len(added),
                postfit_only_count=len(m['postfit_only_observation_ids']),
                active_curved_norads=m['active_curved_norads'],
                RMS_hz=d['arms'][arm]['RMS_hz'],negative_twice_elbo=d['arms'][arm]['negative_twice_elbo']) for arm,m in members.items()}
            row['matched_c_observations_candidate_labels_aliases_priors_budget']=True
            memberships[case,variant]=members;mappings[case,variant]=maps['c0'];scales[case,variant]=effective_scales(root,case);data[case,variant]=d
        rows.append(row)
    receipt=dict(all_terminal=True,all_complete=all(r['status']=='complete' for r in rows),audited=rows,
        new_jobs=4,reused_controls=2,no_denied_inference_reads=True,GPS_errors_opened=False,
        terminal_seal_sha256=sha(HERE/'position_final_terminal_seal.json'),protocol_sha256=sha(HERE/'position_protocol.json'),
        evaluation_source_sha256=sha(__file__))
    write(HERE/'position_inference_audit.json',receipt)
    return receipt,protocol,jobs,memberships,mappings,scales,data


def distance_km(point,reference):
    a,b,c,d=map(math.radians,(*point,*reference));v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 2*6371.0088*math.asin(min(1.,math.sqrt(v)))


def main():
    audited,protocol,jobs,memberships,mappings,scales,data=audit()
    # The inference/read/input audit has now been written. Reference is reporting only.
    reference=[37.849061591561885,-122.48574968092912];rows=[]
    for item,job in zip(audited['audited'],jobs,strict=True):
        row={k:item[k] for k in ('case','variant','status','seconds','reused_control')}
        if item['status']=='complete':
            final=read(Path(job['root'])/'family_cavity/position'/(job['case']+'.json'))
            row['arms']={arm:dict(item['arms'][arm],endpoint_latlon=final['policy_arms'][arm]['endpoint_latlon'],
                position_error_km=distance_km(final['policy_arms'][arm]['endpoint_latlon'],reference)) for arm in ('c0','fitted_c')}
        rows.append(row)
    by_key={(r['case'],r['variant']):r for r in rows};effects=[];attribution=[]
    for case in protocol['cases']:
        ledger=read(HERE/(case+'_additions.json'));added={r['target_observation_id']:r for r in ledger['staged']}
        graph=read(HERE/'graphs'/case/'graph_audit.json');baseline=by_key[case,'baseline']
        for variant in ('additions_proxy','additions_bin_floor'):
            row=by_key[case,variant];effect=dict(case=case,variant=variant)
            if baseline['status']!=row['status'] or row['status']!='complete':
                effect['status']='unavailable';effects.append(effect);continue
            effect['arms']={arm:dict(position_error_change_m=1000*(row['arms'][arm]['position_error_km']-baseline['arms'][arm]['position_error_km']),
                relative_error_change=row['arms'][arm]['position_error_km']/baseline['arms'][arm]['position_error_km']-1,
                frequency_RMS_change_hz=row['arms'][arm]['RMS_hz']-baseline['arms'][arm]['RMS_hz'],
                likelihood_point_change=row['arms'][arm]['likelihood_points']-baseline['arms'][arm]['likelihood_points']) for arm in ('c0','fitted_c')}
            effects.append(effect)
            base=mappings[case,'baseline'];current=mappings[case,variant];base_families={v['norad'] for v in base.values()}
            incumbent_ids=set(scales[case,'baseline']);new_details=[]
            for oid in sorted(set(added)&set(current)):
                a=added[oid];m=current[oid];family=m['norad'];old_same=[i for i,v in base.items() if v['norad']==family]
                current_original=[i for i,v in current.items() if i in incumbent_ids and v['norad']==family]
                new_details.append(dict(observation_id=oid,prediction_id=a['prediction_id'],channel=a['channel'],native_receiver_id=a['native_receiver_id'],
                    start_counter=a['native']['start_counter'],stop_counter=a['native']['stop_counter'],reference_counter=a['reference_counter'],
                    predicted_cfo_hz=a['predicted_cfo_hz'],measured_cfo_hz=a['measured_cfo_hz'],innovation_hz=a['innovation_hz'],
                    zero_fft_bin=a['zero_fft_bin'],donor_count=a['donor_count'],donor_ids=[d['native_observation_id'] for d in a['donors']],
                    membership=m,sigma_hz=scales[case,variant][oid],
                    satellite_family_classification='extension_of_baseline_likelihood_family' if family in base_families else 'newly_accepted_likelihood_family',
                    same_family_baseline_likelihood_original_count=len(old_same),same_family_current_original_likelihood_count=len(current_original)))
            changes=[scales[case,variant][oid]-scales[case,'baseline'][oid] for oid in incumbent_ids]
            attribution.append(dict(case=case,variant=variant,native_added=len(added),new_in_RF_graph=graph['new_in_graph'],new_in_curved_RF_graph=graph['new_in_curved_graph'],
                new_likelihood_count=len(new_details),new_likelihood_identities=new_details,
                added_accepted_postfit_or_likelihood={arm:len(row['arms'][arm]['added_accepted_ids']) for arm in ('c0','fitted_c')},
                baseline_likelihood_norads=sorted(base_families),current_likelihood_norads=sorted({v['norad'] for v in current.values()}),
                newly_accepted_likelihood_norads=sorted({v['norad'] for v in current.values()}-base_families),
                retained_likelihood_ID_count=len(set(base)&set(current)),lost_likelihood_IDs=sorted(set(base)-set(current)),
                gained_incumbent_likelihood_IDs=sorted((set(current)-set(base))-set(added)),
                reassigned_retained_likelihood_IDs=[oid for oid in set(base)&set(current) if identity_signature(base[oid])!=identity_signature(current[oid])],
                incumbent_noise_changed=sum(abs(v)>1e-10 for v in changes),incumbent_sigma_change_range_hz=[min(changes),max(changes)]))
        if all((case,v) in scales for v in ('additions_proxy','additions_bin_floor')):
            proxy=scales[case,'additions_proxy'];floor=scales[case,'additions_bin_floor'];old=set(scales[case,'baseline'])
            assert all(proxy[oid]==floor[oid] for oid in old)
    write(HERE/'position_evaluation.json',dict(schema='coherent-application-regional-evaluation/v1',
        inference_audit_sha256=sha(HERE/'position_inference_audit.json'),post_seal_GPS_reporting_only=True,
        reference_latlon=reference,rows=rows,effects=effects,attribution=attribution,
        frequency_fit_and_position_accuracy_reported_separately=True,held_validation_claim=False,
        uncertainty_calibrated=False,promotion_authorized=False))
    for row in rows:
        print({k:row[k] for k in ('case','variant','status')}, {arm:dict(error_m=1000*a['position_error_km'],RMS_hz=a['RMS_hz'],added_likelihood=len(a['added_curved_ids'])+len(a['added_predictive_ids']),associated=a['accepted_GLRT_count'],denominator=a['total_GLRT_count']) for arm,a in row.get('arms',{}).items()})


if __name__=='__main__':main()
