"""Fixed-endpoint likelihood/membership replay without refitting any prior/position."""
import argparse
import gzip
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import algo02_scan as algo
import recovery
from leo.analysis.research.retained_track_likelihood import PERIOD
from audit_implementation import read,write,sha


def numpy_encoder(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,np.ndarray):return value.tolist()
    raise TypeError(type(value).__name__)


def context_from_saved(root,case):
    """Reconstruct saved model directly; do not call recovery.context/qualify fits."""
    saved=read(root/'family_cavity/position'/(case+'.json'));assert saved['status']=='complete'
    selected=saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(root);scan=algo.load_scan(root,case)
    d=dict(case=case,scan=scan,node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),model=saved['model'],
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'],
        arms=saved['policy_arms'],observations=read(root/case/'observations.json'))
    for element in scan.elements.values():
        provenance=element['provenance']
        assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=scan.receipt['cutoff_utc_ns']
    history=root/'causal_phase_history'/(case+'.json');forecast=read(history.with_name(case+'_forecast.json'))
    model,qualified=algo.validate_history(read(history),forecast,scan,sha(history))
    for key in ('shrinkage','multiplier','nu'):assert d['model'][key]==model[key],key
    assert all(r['validation_time_ns']<=scan.receipt['cutoff_utc_ns'] for r in forecast['transitions'])
    return d


def mapping(d,arm):
    p=recovery.build(d,arm,d['arms'][arm]['phase_reference']);observations={o['observation_id']:o for o in d['observations']};out={}
    for row,index,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=p.scan.tracks[index]
        for oid,value,active in zip(track['observation_ids'],track['values'],p.keep[sl],strict=True):
            if active:
                assert oid not in out
                out[oid]=dict(role='curved',norad=int(p.scan.norads[row['candidate_index']]),
                    native_alias=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(alias))
    for entry in d['entries']:
        track=d['scan'].tracks[entry['track_index']];values=dict(zip(track['observation_ids'],track['values'],strict=True))
        for oid in entry['observation_ids']:
            assert oid not in out
            out[oid]=dict(role='predictive',norad=int(p.scan.norads[entry['candidate_index']]),
                native_alias=round((float(values[oid])-observations[oid]['measured_cfo_hz'])/PERIOD)+int(entry['alias']))
    return out,p


def audit_terminal(protocol_path,terminal_path,name):
    began=time.monotonic();protocol_path=Path(protocol_path);terminal_path=Path(terminal_path)
    protocol=read(protocol_path);terminal=read(terminal_path)
    assert terminal['all_terminal'] and terminal['inputs_and_sources_unchanged'] and not terminal['GPS_evaluation_performed']
    assert terminal['protocol_sha256']==sha(protocol_path) and not terminal['denied_paths']
    for path,h in terminal['output_sha256'].items():assert sha(path)==h,path
    for path,h in dict(protocol['sources_sha256'],**protocol['inputs_sha256']).items():assert sha(path)==h,path
    output=HERE/'scientific_audits'/name;output.mkdir(parents=True,exist_ok=False);audited=[]
    jobs={(j['case'],j['variant']):j for j in protocol['jobs']};seen=set()
    for result in terminal['results']:
        key=result['case'],result['variant'];assert key in jobs and key not in seen;seen.add(key)
        job=jobs[key];root=Path(job['root']);case=job['case'];variant=job['variant']
        execution=read(root/'execution.json');assert execution==result
        receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
        assert not any(r['denied_paths'] for r in receipts)
        paths=sorted({v for r in receipts for v in r['read_paths']})
        assert not any('gps' in Path(p).name.lower() or 'oracle' in Path(p).name.lower() for p in paths)
        row=dict(case=case,variant=variant,status=result['status'],seconds=result['seconds'],
            read_receipt_count=len(receipts),read_receipt_hashes={str(p):sha(p) for p in (root/'read_receipts').glob('*.json')},
            endpoint_replay_performed=False,no_reference_coordinate_used=True,
            read_audit_complete=bool(receipts) and len(receipts)>=3,
            incomplete_read_audit_is_nonqualifying=not (bool(receipts) and len(receipts)>=3))
        if result['status']=='complete':
            assert len(receipts)>=3,'complete inference requires all process read receipts'
            assert len(result['stages'])==2 and all(s['returncode']==0 for s in result['stages'])
            assert result['uid']==1000 and result['seconds']<=240
            d=context_from_saved(root,case);members={};maps={};problems={}
            for arm in ('c0','fitted_c'):
                members[arm]=recovery.membership(d,arm,d['arms'][arm])
                maps[arm],problems[arm]=mapping(d,arm)
            a,b=problems['c0'],problems['fitted_c']
            assert maps['c0']==maps['fitted_c']
            assert np.array_equal(a.keep,b.keep) and np.array_equal(a.alias,b.alias) and a.labels==b.labels
            assert np.array_equal(a.point_noise,b.point_noise) and np.array_equal(a.scan.norads,b.scan.norads)
            for role in ('curved_observation_ids','predictive_observation_ids'):assert members['c0'][role]==members['fitted_c'][role]
            added=set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
            row.update(endpoint_replay_performed=True,matched_c_masks_nativeIDs_labels_aliases_noise_candidates=True,
                original_GLRT_count=len(d['observations'])-len(added),added_native_count=len(added),
                arms={arm:dict(objective_replay_difference=m['objective_replay_difference'],
                    frequency_RMS_hz=d['arms'][arm]['RMS_hz'],negative_twice_elbo=d['arms'][arm]['negative_twice_elbo'],
                    associated_GLRT=m['associated'],total_GLRT=m['total_GLRT'],association_fraction=m['associated']/m['total_GLRT'],
                    likelihood_points=m['likelihood_points'],curved_likelihood_points=m['curved_points'],predictive_likelihood_points=m['predictive_points'],
                    added_curved_IDs=sorted(added&set(m['curved_observation_ids'])),added_predictive_IDs=sorted(added&set(m['predictive_observation_ids'])),
                    added_accepted_IDs=sorted(added&set(m['accepted_observation_ids']))) for arm,m in members.items()})
            full=dict(case=case,variant=variant,likelihood_map=maps['c0'],memberships=members)
            path=output/(case+'-'+variant+'.json.gz')
            serialized=json.dumps(full,indent=2,allow_nan=False,default=numpy_encoder)
            with gzip.open(path,'xt') as f:f.write(serialized+'\n')
            row['full_membership_audit_path']=str(path);row['full_membership_audit_sha256']=sha(path)
        audited.append(row)
    receipt=dict(terminal_source_input_integrity_passed=True,
        all_terminal_inputs_and_reads_audited=all(r['read_audit_complete'] for r in audited),
        all_complete=all(r['status']=='complete' for r in audited),
        audited=audited,cases_audited=len(audited),incomplete_results_retained=[dict(case=r['case'],variant=r['variant'],status=r['status']) for r in audited if r['status']!='complete'],
        implementation_protocol=str(protocol_path),implementation_protocol_sha256=sha(protocol_path),
        terminal_path=str(terminal_path),terminal_sha256=sha(terminal_path),evaluation_protocol_sha256=sha(HERE/'protocol_v2.json'),
        source_sha256=sha(__file__),GPS_error_evaluation_performed=False,
        no_new_position_or_prior_optimization=True,fixed_endpoint_replay_only=True,IQ_calls=0,seconds=time.monotonic()-began)
    write(HERE/(name+'.json'),receipt)
    print({k:v for k,v in receipt.items() if k!='audited'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--terminal',required=True);p.add_argument('--name',required=True);a=p.parse_args()
    assert Path(a.name).name==a.name;audit_terminal(a.protocol,a.terminal,a.name)
