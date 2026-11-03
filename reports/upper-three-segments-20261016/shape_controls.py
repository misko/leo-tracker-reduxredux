"""Bounded wider-timing search with matched calibration removal controls."""
import json
import numpy as np
from search import ROOT,observations,offset_fit
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def link_segments(segments):
    """Join only proposals with substantial shared observations, not time proximity."""
    parts=[set(s['rows']) for s in segments]
    changed=True
    while changed:
        changed=False
        for j in range(len(parts)):
            for k in range(j+1,len(parts)):
                overlap=len(parts[j]&parts[k])
                if overlap>=6 and overlap>=.5*min(len(parts[j]),len(parts[k])):
                    parts[j]|=parts[k];parts.pop(k);changed=True;break
            if changed:break
    return [sorted(s) for s in sorted(parts,key=lambda s:-len(s))]


def extend_continuity(a,rows,available):
    """Extend a segment with raw-CFO cubic continuity, without orbit predictions."""
    available=np.array(available);rows=np.array(rows)
    center=float(np.mean(a['times'][rows]));tt=(a['times'][available]-center)/20.
    design=np.column_stack([np.ones(len(tt)),tt,tt*tt,tt*tt*tt])
    active=np.isin(available,rows)
    value=np.unwrap(a['measured'][available[active]]*2*np.pi/(1/4.4e-6))*(1/4.4e-6)/(2*np.pi)
    coefficient=np.linalg.lstsq(design[active],value,rcond=None)[0]
    for _ in range(5):
        prediction=design@coefficient;residual=circular(a['measured'][available]-prediction)
        take=np.flatnonzero(abs(residual)<=300.)
        chunks=np.split(take,np.flatnonzero(np.diff(a['times'][available[take]])>5.)+1)
        chunk=max(chunks,key=lambda c:(np.isin(available[c],rows).sum(),len(c)))
        active=np.zeros(len(available),bool);active[chunk]=True
        coefficient=np.linalg.lstsq(design[active],(prediction+residual)[active],rcond=None)[0]
    return available[active].tolist()


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz');cal=np.load(ROOT/'calibration-components.npz')
    ctx=json.loads((ROOT/'context.json').read_text());base=json.loads((ROOT/'baseline.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities'])
    prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector']);retained=set(base['retained_candidates'])
    result=dict(timing_grid_s=[-20,20,.1],frequency_scale_hz=125,timing_prior_sigma_s=2,
        qualification='Conditional all-regional carrier-shape diagnostics. Published, no-flexible-clock, '
        'and raw-CFO arms keep observations, RF mapping, geometry, candidates and timing budgets matched. '
        'Every arm fits a track-specific constant offset; this does not validate a physical offset. '
        'No new localization model, no independent identity truth. Calibration was learned on the full scan.',groups=[])
    for group in base['groups']:
        for part,rows_list in enumerate(link_segments(group['continuity_segments'])):
            if len(rows_list)<8:continue
            seed_count=len(rows_list)
            rows_list=extend_continuity(a,rows_list,a[group['name']+'_all_rows'])
            rows=np.array(rows_list);obs=observations(a,ctx,rows);t=obs.times_s
            splits={'all':np.ones(len(rows),bool),'early_to_late':t<=np.median(t),'late_to_early':t>np.median(t)}
            modes=['published','no_clock','raw']
            state={(mode,split):dict(score=np.full(len(bank.numbers),np.inf),timing=np.zeros(len(bank.numbers)),
                offset=np.zeros(len(bank.numbers)),train=np.zeros(len(bank.numbers)),test=np.zeros(len(bank.numbers)))
                for mode in modes for split in splits}
            for shift in np.linspace(-20,20,401):
                pred,vis,_,_=predict_orbits(bank,obs,prior,v[:2],np.full(len(bank.numbers),shift),derivatives=False)
                for mode in modes:
                    residual=circular(a['measured'][rows,None]-cal[mode][rows,None]-pred)
                    for split,train in splits.items():
                        off,tr,te=offset_fit(residual,train)
                        score=train.sum()*(tr/125)**2+(shift/2)**2;score[~vis[train].all(axis=0)]=np.inf
                        s=state[mode,split];take=score<s['score']
                        for key,val in [('score',score),('offset',off),('train',tr),('test',te)]:s[key][take]=val[take]
                        s['timing'][take]=shift
            row=dict(group=group['name'],receiver=group['receiver'],channel=group['channel'],part=part,
                rows=rows_list,count=len(rows_list),unassociated=int((~a['associated'][rows]).sum()),
                linked_seed_count=seed_count,extension='Orbit-blind raw-CFO cubic, 300 Hz threshold, 5 s maximum gap, 5 iterations',
                time_limits_s=[float(t.min()),float(t.max())],arms={})
            for (mode,split),s in state.items():
                row['arms'].setdefault(mode,{})[split]=[dict(satellite=int(bank.numbers[j]),retained=int(bank.numbers[j]) in retained,
                    timing_s=float(s['timing'][j]),offset_hz=float(s['offset'][j]),
                    training_rms_hz=float(s['train'][j]),test_rms_hz=float(s['test'][j]) if (~splits[split]).any() else None,
                    score=float(s['score'][j])) for j in np.argsort(s['score'])[:8]]
            result['groups'].append(row)
            (ROOT/'shape-controls.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            print(json.dumps(dict(group=group['name'],count=len(rows),arms={mode:{split:row['arms'][mode][split][0] for split in splits} for mode in modes})),flush=True)


if __name__=='__main__':main()
