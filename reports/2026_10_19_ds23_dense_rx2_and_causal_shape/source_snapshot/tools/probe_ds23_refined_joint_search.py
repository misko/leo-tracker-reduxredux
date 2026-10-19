"""Bounded simultaneous family replacements with the newly precise active data."""

import argparse
import itertools
from pathlib import Path
import numpy as np
from ds23_family_screen import screen_family
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE,context,refit
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

OUT=ROOT/'reports/2026_10_19_ds23_refined_joint_search'


def combinations(pools,all_labels):
    """Permit simultaneous swaps while forbidding accidental family mergers."""
    families=list(pools);operations=[]
    for choice in itertools.product(*[[None]+pools[j] for j in families]):
        moved={j:r for j,r in zip(families,choice,strict=True) if r is not None}
        if not moved:continue
        final=[moved[j]['target'] if j in moved else j for j in all_labels]
        if len(set(final))!=len(final):continue
        operations.append(dict(families=list(moved),changes=[c for r in moved.values() for c in r['changes']]))
    return operations


def setup(case):
    scan,node,keep,powers,noise,radio,model,old,offsets=context(case,True)
    catalogue=read(CATALOGUE/(case+'_companion.json'));base=catalogue['chosen']
    node=changed_node(scan,node,base['proposal']['changes'])
    return scan,node,keep,powers,noise,model,catalogue,base


def prepare(case):
    OUT.mkdir(parents=True,exist_ok=True)
    scan,node,keep,powers,noise,model,catalogue,base=setup(case);p=problem(scan,node,'c0',keep)
    assert all(r['component']==node['seed']['rows'][k]['component'] for k,r in enumerate(p.rows))
    endpoint=np.array(base['arms']['c0']['endpoint_east_north_km']);state=base['arms']['c0']['state']
    anchors=[np.zeros(2),endpoint]+[np.array(r['arms']['c0']['endpoint_east_north_km']) for r in catalogue['trials'] if r.get('paired_valid') and r is not base]
    anchors += [np.array([e,n]) for e in (-12.5,12.5) for n in (-12.5,12.5)]
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))));means=forecast_phase_mean(receipts,model['shrinkage'])
    widths=np.array(widths)*model['multiplier'];proposals={};screen_receipts=[]
    for ai,anchor in enumerate(anchors):
        frequency,elevation,derivative=phase_linear_frequency(scan.geometry,*latlon(anchor))
        for source in p.labels:
            members=[k for k,r in enumerate(p.rows) if r['candidate_index']==source]
            active_members=[k for k in members if keep[p.slices[k]].any()]
            if not active_members:continue
            curves=[]
            for k in active_members:
                i,sl=p.members[k],p.slices[k];tr=scan.tracks[i];active=keep[sl];ix=scan.index[i][active];q=tr['rf_hz']/11.5e9
                y=tr['values']-scan.hardware(tr,np.array(state['beta']))-q*scan.rx_basis[i]@np.array(state['smooth'])[tr['receiver']-1]
                sigma=np.array([noise.get(o,s) for o,s in zip(tr['observation_ids'],p.point_noise[sl],strict=True)])[active]
                curves.append(dict(observed=y[active],predicted=q*(frequency[:,ix]+derivative[:,ix]*means[:,None]),
                    derivative=q*derivative[:,ix],sigma=sigma,power=powers[k],visible=np.min(elevation[:,ix],axis=1)>=0))
            screen=screen_family(curves,widths);finite=[int(j) for j in np.argsort(screen['cost']) if np.isfinite(screen['cost'][j])]
            incumbent_cost=float(screen['cost'][source]);screen_receipts.append(dict(anchor=ai,source=int(source),
                source_norad=int(scan.norads[source]),incumbent_cost=incumbent_cost if np.isfinite(incumbent_cost) else None,
                top=[dict(index=j,norad=int(scan.norads[j]),cost=float(screen['cost'][j])) for j in finite[:3]]))
            for j in finite[:3]:
                if j==source:continue
                aliases={k:int(a[j]) for k,a in zip(active_members,screen['aliases'],strict=True)}
                changes=[dict(row_index=k,candidate_index=j,alias=aliases.get(k,int(node['aliases'][k]))) for k in members]
                gap=float(screen['cost'][j]-incumbent_cost) if np.isfinite(incumbent_cost) else float(screen['cost'][j])
                r=dict(source=int(source),target=j,norad=int(scan.norads[j]),changes=changes,screen_delta=gap,anchor=ai)
                key=(source,j)
                if key not in proposals or gap<proposals[key]['screen_delta']:proposals[key]=r
    precise=int(base['proposal']['index']);pools={}
    # Three previously tested alternatives from full RF evidence, including isolated failures.
    prior=sorted([r for r in catalogue['trials'] if 'arms' in r and r['proposal']['index']!=precise],
                 key=lambda r:r['arms']['c0']['negative_twice_elbo'])[:3]
    pools[precise]=[dict(source=precise,target=r['proposal']['index'],changes=r['proposal']['changes']) for r in prior]
    others=sorted({r['source'] for r in proposals.values() if r['source']!=precise},
                  key=lambda j:min(r['screen_delta'] for r in proposals.values() if r['source']==j))[:3]
    for source in others:pools[source]=sorted([r for r in proposals.values() if r['source']==source],key=lambda r:r['screen_delta'])[:2]
    operations=combinations(pools,p.labels)
    write(OUT/(case+'_plan.json'),dict(case=case,baseline=base,base_node=node,mask=keep,pools={str(k):v for k,v in pools.items()},
        operations=operations,anchors=anchors,screen_receipts=screen_receipts,catalogue_size=len(scan.norads),
        source_sha256=sha(Path(__file__)),catalogue_input_sha256=sha(CATALOGUE/(case+'_companion.json')),
        no_GPS_used=True,proposal_rounds=2,proposal_steps=12,final_rounds=5,final_steps=48,workers=2,
        selection_uses_RF_only=True,mergers_forbidden_but_simultaneous_swaps_permitted=True))
    print(case,'planned',len(operations),'operations across',len(pools),'families',flush=True)


def worker(case,worker_id):
    path=OUT/(case+'_plan.json');plan=read(path);assert plan['source_sha256']==sha(Path(__file__))
    scan,node,keep,powers,noise,model,catalogue,base=setup(case)
    for number,op in enumerate(plan['operations']):
        if number%2!=worker_id:continue
        candidate=changed_node(scan,node,op['changes']);r=refit(scan,candidate,keep,powers,noise,model,'c0',rounds=2,steps=12)
        failed=[t['component'] for t in r['gates']['tracks'] if not t['compatible']]
        write(OUT/f'{case}_proposal_{number:03d}.json',dict(number=number,operation=op,
            negative_twice_elbo=r['negative_twice_elbo'],endpoint_east_north_km=r['endpoint_east_north_km'],
            RMS_hz=r['RMS_hz'],failed_tracks=failed,plan_sha256=sha(path),source_sha256=sha(Path(__file__))))
        if number%10<2:print(case,'worker',worker_id,'proposal',number,'/',len(plan['operations']),flush=True)


def finalize(case):
    plan_path=OUT/(case+'_plan.json');plan=read(plan_path);records=[]
    for number in range(len(plan['operations'])):
        r=read(OUT/f'{case}_proposal_{number:03d}.json');assert r['plan_sha256']==sha(plan_path);records.append(r)
    scan,node,keep,powers,noise,model,catalogue,base=setup(case);trials=[]
    for proposal in sorted(records,key=lambda r:r['negative_twice_elbo'])[:6]:
        candidate=changed_node(scan,node,proposal['operation']['changes'])
        arms={arm:refit(scan,candidate,keep,powers,noise,model,arm) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks'])
        trials.append(dict(proposal=proposal,arms=arms,paired_valid=valid))
        write(OUT/(case+'_final_partial.json'),dict(case=case,trials=trials))
        print(case,'finalist',proposal['number'],'families',len(proposal['operation']['families']),'valid',valid,flush=True)
    improved=[r for r in trials if r['paired_valid'] and r['arms']['c0']['negative_twice_elbo']<base['arms']['c0']['negative_twice_elbo']-1e-6]
    chosen=min(improved,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if improved else None
    write(OUT/(case+'.json'),dict(case=case,trials=trials,chosen=chosen,baseline=base,
        reported_arms=base['arms'] if chosen is None else chosen['arms'],proposal_count=len(records),
        no_GPS_used=True,paired_c=True,all_original_points_preserved=True,plan_sha256=sha(plan_path),source_sha256=sha(Path(__file__))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--stage',choices=['prepare','worker','finalize'],required=True);parser.add_argument('--worker-id',type=int,choices=[0,1])
    args=parser.parse_args()
    if args.stage=='prepare':prepare(args.case)
    elif args.stage=='worker':worker(args.case,args.worker_id)
    else:finalize(args.case)
