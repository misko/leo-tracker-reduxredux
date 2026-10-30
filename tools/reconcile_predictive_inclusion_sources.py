"""Index saved position trials by physical observation ownership, not filenames."""
import argparse,csv,hashlib
from collections import Counter,defaultdict
from pathlib import Path
from debug_fast_graph_unassociated import read,write


def coverage(target_ids,curve_ids):
    a=set(target_ids);b=set(curve_ids);n=len(a&b)
    return 'none' if not n else 'full_curve' if b<=a else 'partial_curve'


def trial_role(protocol):
    if protocol.get('curved_targets_calibrate_receiver') or protocol.get('target_used_for_calibration') or protocol.get('target_calibrates_receiver'):
        return 'calibration_participating'
    if 'family_prior' in protocol or protocol.get('target_used_for_calibration') is False or protocol.get('target_calibrates_receiver') is False:
        return 'predictive_only'
    return 'unresolved_role'


def recorded_checks(control,trial,replay):
    if not control or set(control.get('arms',{}))!={'c0','fitted_c'} or set(trial.get('arms',{}))!={'c0','fitted_c'}:
        return 'incomplete_paired_output'
    if not control.get('paired_valid') or not trial.get('paired_valid'):
        return 'recorded_pair_rejected'
    if replay is None:return 'paired_pass_replay_missing'
    return 'paired_and_replay_pass' if replay.get('all_verified') else 'recorded_replay_rejected'


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);hashes={};cache={}
    def load(p,retain=False):
        if str(p) in cache:return cache[str(p)]
        data=p.read_bytes();hashes[str(p)]=hashlib.sha256(data).hexdigest()
        import json
        result=json.loads(data)
        if retain:cache[str(p)]=result
        return result
    queue=load(args.study/'systematic-annotation-v1/protocol.json')['rows'];byid={r['track_id']:r for r in queue}
    curves={};byobservation=defaultdict(set)
    for job in queue:
        inv=load(Path(job['inventory']),retain=True);t=next(t for t in inv['tracks'] if t['track_id']==job['track_id'])
        curves[job['track_id']]=set(t['observation_ids'])
        for oid in t['observation_ids']:byobservation[oid].add(job['track_id'])
    role_rows=list(csv.DictReader(args.roles.open()));hashes[str(args.roles)]=hashlib.sha256(args.roles.read_bytes()).hexdigest()
    candidates=[r for r in role_rows if r['next_action']=='supported_predictive_identity_needs_inclusion_source']
    protocols=sorted(args.study.rglob('protocol.json'));trials=[];unresolved=[];bytrack=defaultdict(list)
    for path in protocols:
        p=load(path);folder=path.parent
        if not (folder/'control.json').exists():continue
        control=load(folder/'control.json')
        files=sorted(set(folder.glob('target_*.json'))|{f for f in [folder/'new_family.json',folder/'combined.json'] if f.exists()})
        for f in files:
            r=load(f);entries=r.get('target_entries')
            if not isinstance(entries,list) or not entries:
                unresolved.append(dict(source=str(f),reason='no target_entries; requires separate schema review'));continue
            ids=set();legacy=[]
            for e in entries:
                if e.get('observation_ids'):ids.update(e['observation_ids'])
                elif e.get('track_id') in curves:
                    tid=e['track_id'];job=byid[tid]
                    if p.get('job',{}).get('job_id')!=job['job_id']:raise ValueError('legacy target belongs to another scan')
                    ids.update(curves[tid]);legacy.append(tid)
                else:unresolved.append(dict(source=str(f),reason='unresolved entry identity',component=e.get('component')))
            matching=set(t for oid in ids for t in byobservation.get(oid,[]))
            replay_path=folder/'exact_owner_replay.json';replay=load(replay_path) if replay_path.exists() else None
            # A replay must actually cover this saved trial; a sibling's pass is insufficient.
            covered=bool(replay and str(f) in replay.get('source_hashes',{}))
            if covered and replay['source_hashes'][str(f)]!=hashes[str(f)]:raise ValueError('replay refers to changed trial')
            status=recorded_checks(control,r,replay if covered else None)
            record=dict(source=str(f),protocol=str(path),role=trial_role(p),status=status,
                target_points=len(ids),matched_inventory_curves=len(matching),legacy_curve_ID_resolution=legacy,
                replay_source=str(replay_path) if covered else '',qualification_not_inferred=True)
            trials.append(record)
            for tid in sorted(matching):
                match=dict(record,track_id=tid,coverage=coverage(ids,curves[tid]),overlap_points=len(ids&curves[tid]))
                bytrack[tid].append(match)
    write(out/'trial_registry.json',trials);write(out/'curve_trial_links.json',dict(bytrack));write(out/'unresolved_schemas.json',unresolved)
    reconciliation=[];pending=[]
    for row in candidates:
        matches=bytrack[row['track_id']]
        full=[m for m in matches if m['coverage']=='full_curve' and m['role']=='predictive_only']
        if full:state='existing_predictive_trial_found'
        elif matches:state='only_other_role_or_partial_trial_found'
        else:state='no_supported_schema_trial_found'
        reconciliation.append(dict(row,reconciled_state=state,predictive_full_curve_trials=len(full),
            recorded_passes=sum(m['status']=='paired_and_replay_pass' for m in full),
            trial_sources=';'.join(m['source'] for m in matches)))
        if not full:pending.append(dict(byid[row['track_id']],validation=str(Path(row['primary_source']).parent),registry_state=state))
    pending.sort(key=lambda r:(-r['points'],r['track_id']))
    with (out/'supported_reconciliation.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(reconciliation[0]),lineterminator='\n');w.writeheader();w.writerows(reconciliation)
    write(out/'pending_candidates.json',pending)
    write(out/'summary.json',dict(inventory_curves=len(curves),protocols_scanned=len(protocols),indexed_trial_outputs=len(trials),
        linked_curves=len(bytrack),unresolved_outputs=len(unresolved),supported_missing_link_rows=len(candidates),
        reconciliation_counts=dict(Counter(r['reconciled_state'] for r in reconciliation)),pending_candidate_count=len(pending),
        no_new_associations=True,scope=str(args.study),source_hashes=hashes))
    print('reconciliation',dict(Counter(r['reconciled_state'] for r in reconciliation)),'pending',len(pending),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','roles','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
