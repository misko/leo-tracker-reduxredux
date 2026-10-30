"""Timestamp-only fixed-versus-shifted block coverage for the full inventory."""
import argparse,csv,hashlib
from collections import Counter
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import geometry_partition_schedule,shifted_geometry_partition_schedule


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);sources={};cache={};rows=[];plans={}
    def load(path):sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    ledger=list(csv.DictReader(args.ledger.open()));sources[str(args.ledger)]=hashlib.sha256(args.ledger.read_bytes()).hexdigest()
    seed_pool=[20261029,94721,4081]+np.random.default_rng(20261029).integers(0,2**31-1,64).tolist()
    for row in ledger:
        job=row['job_id']
        if job not in cache:
            inv=load(args.study/'all-large-track-recovery'/job/'inventory.json');root=Path(inv['job']['root']);case=inv['job']['case']
            tracks=load(root/case/'tracks.json');saved=load(root/'family_cavity/position'/f'{case}.json')
            node=saved['selected']['node'] if saved['accepted'] else saved['baseline_node'];bykey={t['key']:t for t in tracks}
            full=np.concatenate([bykey[r['component']]['times'] for r in node['seed']['rows']])
            cache[job]=(inv,bykey,full)
        inv,bykey,base_times=cache[job];track=bykey[row['component']];focus=np.asarray(track['times']);times=np.r_[base_times,focus]
        # This is a whole-native-curve geometry audit. Partly occupied curves
        # still require reconstruction and annotation of only unused points.
        occupied=set(inv['policy']['c0']['proposed_associated_ids'])|set(inv['policy']['fitted_c']['proposed_associated_ids'])
        overlap=len(occupied&set(track['observation_ids']))
        fixed=geometry_partition_schedule(times,focus,seeds=seed_pool);shifted=shifted_geometry_partition_schedule(times,focus,seeds=seed_pool)
        prior=row.get('predictive_recheck_state') or row['state']
        rows.append(dict(track_id=row['track_id'],job_id=job,scan=row['label'],component=row['component'],points=len(focus),span_s=float(np.ptp(focus)),
            current_owned_points=overlap,whole_curve_unowned=overlap==0,prior_status=prior,fixed_ready=fixed['ready'],shifted_ready=shifted['ready'],
            fixed_usable_sets=len(fixed['selected']),shifted_usable_sets=len(shifted['selected']),new_geometry_support=not fixed['ready'] and shifted['ready']))
        plans[row['track_id']]=dict(fixed=fixed,shifted=shifted,target_times_s=focus)
    if len(rows)!=len({r['track_id'] for r in rows}):raise ValueError('duplicate inventory rows')
    with (out/'rows.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    summary=dict(curves=len(rows),transition_counts=dict(Counter(f"{r['fixed_ready']}->{r['shifted_ready']}" for r in rows)),
        newly_usable_wholly_unowned=sum(r['new_geometry_support'] and r['whole_curve_unowned'] for r in rows),
        new_wholly_unowned_previously_insufficient=sum(r['new_geometry_support'] and r['whole_curve_unowned'] and r['prior_status']=='insufficient_partitions' for r in rows),
        phase_or_frequency_used_for_selection=False,GPS_used=False,association_or_acceptance_changed=False,
        caveat='Whole original curves only. Partial occupancy requires separate unused-fragment reconstruction. Geometric eligibility is not satellite validation.')
    write(out/'summary.json',summary);write(out/'plans.json',plans);write(out/'sources.json',sources)
    write(out/'protocol.json',dict(seed_pool=seed_pool,block_s=12,guard_s=2,minimum_train=8,minimum_held=4,required_distinct_sets=3,
        grouping='one scanwide shifted origin per seed; simultaneous observations grouped, guards retained',selection='all ledger rows, no RF or position-based filtering'))
    print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','ledger','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
