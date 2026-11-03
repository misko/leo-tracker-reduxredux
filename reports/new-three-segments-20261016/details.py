"""Additional conditional checks: shared timing, full objective, causal TLE age."""
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from search import ROOT,observations
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.regional_position_score import circular
from leo.analysis.hard60_score import predict_orbits
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    ctx=json.loads((ROOT/'context.json').read_text());base=json.loads((ROOT/'baseline.json').read_text())
    results=json.loads((ROOT/'search-results.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities'])
    prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector'])
    groups=[g for g in results['groups'] if g['selection']=='continuity_1']
    # Choose shared timing on the other two trajectories, then identity from the
    # tested trajectory's training half. Its held half selects neither parameter.
    grid=np.linspace(-5,5,201);cost=np.zeros((len(grid),len(groups)));cache=[]
    for i,shift in enumerate(grid):
        entry=[]
        for gidx,g in enumerate(groups):
            rows=np.array(g['rows']);obs=observations(a,ctx,rows)
            pred,vis,_,_=predict_orbits(bank,obs,prior,v[:2],np.full(len(bank.numbers),shift),derivatives=False)
            residual=circular(a['measured'][rows,None]-a['correction'][rows,None]-pred)
            score=np.sum((residual/125.)**2,axis=0)
            score[~vis.all(axis=0)]=np.inf
            cost[i,gidx]=score.min()
            entry.append((residual,vis))
        cache.append(entry)
    shared=[]
    for j,g in enumerate(groups):
        i=int(np.argmin(cost[:,np.arange(len(groups))!=j].sum(axis=1)+(grid/2)**2))
        residual,vis=cache[i][j];rows=np.array(g['rows']);t=a['times'][rows]
        splits={'early_to_late':t<=np.median(t),'late_to_early':t>np.median(t)}
        for split,train in splits.items():
            score=np.mean(residual[train]**2,axis=0);score[~vis[train].all(axis=0)]=np.inf;k=int(np.argmin(score))
            shared.append(dict(group=g['group'],split=split,timing_s=float(grid[i]),satellite=int(bank.numbers[k]),
                training_count=int(train.sum()),test_count=int((~train).sum()),
                training_rms_hz=float(np.sqrt(np.mean(residual[train,k]**2))),
                test_rms_hz=float(np.sqrt(np.mean(residual[~train,k]**2)))))
    joint_i=int(np.argmin(cost.sum(axis=1)+(grid/2)**2))
    joint=[]
    for j,g in enumerate(groups):
        residual,vis=cache[joint_i][j];s=np.mean(residual**2,axis=0);s[~vis.all(axis=0)]=np.inf;k=int(np.argmin(s))
        joint.append(dict(group=g['group'],satellite=int(bank.numbers[k]),rms_hz=float(np.sqrt(s[k]))))
    # Full original mixture objective at edited timings; no claim of converged refit.
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2')
    job,document,terminal,stages=store.plot_evidence('075b34f9532dd9f7caf6c70830e4e8e8')
    source=load_input(document);prepared,nodes=prepare_views(source)
    base['terminal_sha256']=job['terminal']['sha256']
    numbers=terminal['candidate_numbers'];lookup={int(n):i for i,n in enumerate(bank.numbers)}
    selected=bank.select([lookup[n] for n in numbers])
    model,fit,audit=selected_model(prepared,selected,prior,nodes,terminal,stages)
    nv=np.array(fit['nuisance']);original=np.array(fit['vector']);tau=original[7]+model.basis@original[8:]
    trials={}
    for name,changes in [('baseline',{}),('retime_66854',{66854:-1.5}),('retime_58362',{58362:-1.25}),
                         ('retime_both',{66854:-1.5,58362:-1.25})]:
        target=tau.copy()
        for num,value in changes.items():target[numbers.index(num)]=value
        vv=original.copy();vv[7]=target.mean();vv[8:]=model.basis.T@(target-vv[7])
        np.testing.assert_allclose(vv[7]+model.basis@vv[8:],target,atol=1e-12,rtol=0)
        e=model.evaluate_joint(vv,nv);terms=e[3]
        best=terms.responsibilities.argmax(axis=1)
        associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
        target_counts=[]
        for g,num in zip(groups,[66854,58362,57864]):
            rows=np.array(g['rows'])
            target_counts.append(dict(group=g['group'],intended_satellite=num,
                associated=int(associated[rows].sum()),
                intended_associated=int(np.sum(associated[rows]&(np.array(numbers)[best[rows]]==num)))))
        trials[name]=dict(objective=float(e[0]),NLL=float(terms.nll),associated=int(associated.sum()),groups=target_counts)
    donors={}
    for num in [66854,58362]:
        rows=np.flatnonzero(a['associated']&(a['best_number']==num))
        donors[str(num)]=dict(saved_timing_s=float(tau[numbers.index(num)]),points=[dict(row=int(r),
            receiver=int(a['receiver'][r])+1,channel=int(a['channel'][r]),time_s=float(a['times'][r])) for r in rows])
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshots=archive.list_snapshots()
    selected_snapshot=next(s for s in snapshots if s.digest==terminal['provenance']['tle_sha256']
        and s.collected_utc_ns==terminal['provenance']['tle_collected_utc_ns'])
    origin=ctx['source_origin_ns'];fmt=lambda t:datetime.fromtimestamp(t/1e9,timezone.utc).isoformat()
    tle=[]
    for provider in ['huggingface','space-track']:
        snap=archive.select_latest_before(origin,provider)
        cat=parse_element_sets(archive.read(snap));epochs=cat.element_epoch_utc_ns();look={int(n):i for i,n in enumerate(cat.satellite_numbers)}
        tle.append(dict(provider=provider,digest=snap.digest,collected_utc=fmt(snap.collected_utc_ns),
            collection_age_minutes=(origin-snap.collected_utc_ns)/6e10,
            candidates=[dict(satellite=num,element_epoch_utc=fmt(epochs[look[num]]),
                element_age_hours=(origin-epochs[look[num]])/3.6e12) for num in [66854,58362,57864] if num in look]))
    base['snapshot_provider']=selected_snapshot.provider
    base['snapshot_collection_age_s']=(origin-selected_snapshot.collected_utc_ns)/1e9
    base['snapshot_collected_utc']=fmt(selected_snapshot.collected_utc_ns)
    base['recording_origin_utc']=fmt(origin)
    (ROOT/'baseline.json').write_text(json.dumps(base,indent=2)+'\n')
    result=dict(shared_timing_leave_one_track_out=shared,all_three_shared_timing_s=float(grid[joint_i]),
        all_three_shared_fits=joint,full_objective_timing_trials=trials,saved_candidate_support=donors,
        causal_snapshots=tle,qualification='Conditional diagnostics with full-scan receiver calibration '
        'and position frozen. Leave-one-track-out timing is fitted using the other two inspected '
        'trajectories; satellite identity uses only the training half of the tested trajectory. '
        'Retiming trials are objective evaluations, not accepted optimized models.')
    (ROOT/'details.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
