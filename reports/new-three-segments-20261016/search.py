"""Matched conditional all-regional searches; no changes to saved associations."""
import json
from pathlib import Path
import numpy as np
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular, ALIAS_HZ

ROOT=Path(__file__).resolve().parent


def offset_fit(residual, train):
    """Fit a constant circular offset using training samples only."""
    phase=residual[train]*2*np.pi/ALIAS_HZ
    anchor=np.angle(np.mean(np.exp(1j*phase),axis=0))*ALIAS_HZ/(2*np.pi)
    lifted=anchor+np.mean(circular(residual[train]-anchor),axis=0)
    error=circular(residual-lifted)
    return circular(lifted), np.sqrt(np.mean(error[train]**2,axis=0)), np.sqrt(np.mean(error[~train]**2,axis=0)) if (~train).any() else np.zeros(residual.shape[1])


def observations(a,ctx,rows):
    return PositionObservations(tuple(ctx['window_ids'][i] for i in rows),a['times'][rows],
        a['measured'][rows],a['rf'][rows],a['receiver'][rows],a['channel'][rows],np.ones(len(rows)))


def main():
    a=np.load(ROOT/'baseline.npz'); b=np.load(ROOT/'orbit-bank.npz')
    ctx=json.loads((ROOT/'context.json').read_text()); baseline=json.loads((ROOT/'baseline.json').read_text())
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities'])
    prior=RegionalPrior(**ctx['prior']); v=np.array(ctx['vector']); retained=set(baseline['retained_candidates'])
    output=dict(qualification='Conditional frequency-shape fits at the saved full-scan position/calibration, '
        'not an independent localization evaluation. c=0 is a fixed-parameter sensitivity control, '
        'with no reoptimization of the other saved parameters. Candidate/time/offset selection in '
        'temporal tests uses only each training half. Segment extraction uses the full inspected interval.',
        timing_grid_absolute_s=[-5,5,.05],frequency_sigma_hz=125.,timing_prior_sigma_s=2.,groups=[])
    for group in baseline['groups']:
        # Analyze each distinct continuity proposal and the complete unassociated set.
        selections=[('all_unassociated',a[group['name']+'_unassociated_rows'])]
        selections += [(f'continuity_{j+1}',np.array(segment['rows'])) for j,segment in enumerate(group['continuity_segments'])]
        for selection,rows in selections:
            if len(rows)<4: continue
            obs=observations(a,ctx,rows)
            full_y=a['measured'][rows]-a['correction'][rows]
            y0=full_y+v[6]*(a['rf'][rows]-ctx['rf_center_hz'])/1e9
            ys={'fitted-c':full_y,'zero-c-fixed':y0}
            splits={'all':np.ones(len(rows),bool),'early_to_late':obs.times_s<=np.median(obs.times_s),
                    'late_to_early':obs.times_s>np.median(obs.times_s)}
            records=dict(group=group['name'],selection=selection,rows=rows.tolist(),count=len(rows),
                         time_limits_s=[float(obs.times_s.min()),float(obs.times_s.max())],arms={})
            # Saved timings for retained satellites; common timing for omitted candidates.
            pred,vis,_,_=predict_orbits(bank,obs,prior,v[:2],a['shifts'],derivatives=False)
            eligible=vis.all(axis=0)
            for arm,y in ys.items():
                residual=circular(y[:,None]-pred)
                offset,rms,_=offset_fit(residual,splits['all'])
                raw=np.sqrt(np.mean(residual**2,axis=0))
                slope=(obs.times_s-obs.times_s.mean()) @ circular(residual-offset) / np.sum((obs.times_s-obs.times_s.mean())**2)
                def item(j):
                    return dict(satellite=int(bank.numbers[j]),retained=int(bank.numbers[j]) in retained,
                        timing_s=float(a['shifts'][j]),offset_hz=float(offset[j]),raw_rms_hz=float(raw[j]),
                        offset_removed_rms_hz=float(rms[j]),residual_slope_hz_s=float(slope[j]))
                rank=np.argsort(np.where(eligible,rms,np.inf))
                rr=np.argsort(np.where(eligible,raw,np.inf))
                records['arms'][arm]=dict(saved_timing_offset=[item(j) for j in rank[:8]],
                    saved_timing_absolute=[item(j) for j in rr[:8]],temporal={})
            # Both c arms, identical candidate/time grid/priors. Never optimize a test score.
            state={(arm,split,mode):dict(score=np.full(len(bank.numbers),np.inf),timing=np.zeros(len(bank.numbers)),
                    offset=np.zeros(len(bank.numbers)),train=np.zeros(len(bank.numbers)),test=np.zeros(len(bank.numbers)))
                    for arm in ys for split in splits for mode in ('timing_only','timing_and_offset')}
            for shift in np.linspace(-5,5,201):
                pred,vis,_,_=predict_orbits(bank,obs,prior,v[:2],np.full(len(bank.numbers),shift),derivatives=False)
                for arm,y in ys.items():
                    residual=circular(y[:,None]-pred)
                    for split,train in splits.items():
                        for mode in ('timing_only','timing_and_offset'):
                            if mode=='timing_only':
                                offset=np.zeros(len(bank.numbers))
                                tr=np.sqrt(np.mean(residual[train]**2,axis=0))
                                te=np.sqrt(np.mean(residual[~train]**2,axis=0)) if (~train).any() else np.zeros(len(bank.numbers))
                            else:offset,tr,te=offset_fit(residual,train)
                            score=train.sum()*(tr/125.)**2+(shift/2.)**2
                            score[~vis[train].all(axis=0)]=np.inf
                            s=state[arm,split,mode]; take=score<s['score']
                            for key,val in [('score',score),('offset',offset),('train',tr),('test',te)]:s[key][take]=val[take]
                            s['timing'][take]=shift
            for (arm,split,mode),s in state.items():
                train=splits[split]
                ranked=[dict(satellite=int(bank.numbers[j]),retained=int(bank.numbers[j]) in retained,
                    timing_s=float(s['timing'][j]),offset_hz=float(s['offset'][j]),
                    training_rms_hz=float(s['train'][j]),test_rms_hz=float(s['test'][j]) if (~train).any() else None,
                    training_score=float(s['score'][j])) for j in np.argsort(s['score'])[:8]]
                records['arms'][arm]['temporal'][split+'_'+mode]=dict(training_count=int(train.sum()),
                    test_count=int((~train).sum()),ranked=ranked)
            output['groups'].append(records)
            (ROOT/'search-results.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
            print(json.dumps(dict(group=group['name'],selection=selection,count=len(rows),
                saved=records['arms']['fitted-c']['saved_timing_offset'][:2],
                forward=records['arms']['fitted-c']['temporal']['early_to_late_timing_and_offset']['ranked'][:2],
                reverse=records['arms']['fitted-c']['temporal']['late_to_early_timing_and_offset']['ranked'][:2])),flush=True)


if __name__=='__main__':main()
