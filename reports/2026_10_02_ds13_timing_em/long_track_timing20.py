"""Timing-only +/-20s diagnostic on frozen longest-track observations."""
import copy
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT.parent/'2026_10_02_multiscan_localization'),
              str(ROOT.parent/'2026_10_02_localization_benchmark')]


def search(cost, half_width=20.):
    from scipy.optimize import minimize_scalar
    grid=np.linspace(-half_width,half_width,801)
    values=np.array([cost(x) for x in grid])
    best=int(np.argmin(values)); delta=float(grid[best]); value=float(values[best])
    minima=np.flatnonzero((values<=np.r_[np.inf,values[:-1]]) &
                         (values<=np.r_[values[1:],np.inf]))
    for j in minima:
        lo,hi=grid[max(0,j-1)],grid[min(len(grid)-1,j+1)]
        fit=minimize_scalar(cost,bounds=(lo,hi),method='bounded',options={'xatol':1e-8})
        if fit.fun<value: delta,value=float(fit.x),float(fit.fun)
    return delta,value,grid,values


def run():
    from all_visible_bank import load_expanded_scan
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.sky.propagation import parse_element_sets
    from residual_trend_audit import stats
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source=ROOT/'later-tle-timing-aligned-v2/receipt.json'
    receipt=json.loads(source.read_text())
    tle=Path(receipt['latest_snapshot']['path'])
    hashes={**receipt['source_hashes'],**snapshot_files([__file__,source,tle])}
    assert_snapshot_unchanged(hashes)
    catalogue=parse_element_sets(tle.read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    tracks=sorted([t for t in receipt['tracks'] if np.ptp(t['time_s'])>=70],
                  key=lambda t:-np.ptp(t['time_s']))
    loaded={};results=[]
    fig,axes=plt.subplots(len(tracks),2,figsize=(14,15))
    for k,track in enumerate(tracks):
        session=track['session']
        if session not in loaded:
            data=load_expanded_scan(session)
            profile=json.loads((ROOT/'pruned-position-profile-grid'/f'{session}.json').read_text())
            oldfit=next(p['best'] for p in profile['positions'] if p['label']=='truth')
            scan=next(s for s in receipt['scans'] if s['session']==session)
            satellites=np.asarray(profile['satellite_indices'],int)
            indices=[lookup[int(n)] for n in data.numbers[satellites]]
            pos,vel,valid=propagate_candidate_states(catalogue,indices,scan['origin_utc_ns'],data.nodes,np.array([0.]))
            assert list(valid)==indices
            newer=copy.copy(data);newer.position=data.position.copy();newer.velocity=data.velocity.copy()
            newer.position[satellites]=pos[:,0];newer.velocity[satellites]=vel[:,0]
            loaded[session]=[(data,oldfit,'old'),(newer,scan['later_fit'],'later')]
        rows=np.array(track['rows']);times=np.array(track['time_s'])
        for col,(data,fit,variant) in enumerate(loaded[session]):
            satellite=int(np.flatnonzero(data.numbers==track['catalog_number'])[0])
            parameters=np.asarray(fit['parameters']).copy();tau=parameters[6+satellite]
            assert times.min()+tau-20>=data.nodes.min() and times.max()+tau+20<=data.nodes.max()
            paired=np.full(len(rows),satellite)
            baseline,visible=data.predict(parameters,rows,paired)
            assert np.all(visible)
            original=np.array(track[variant+'_residual_hz']);factor=11.085e9/data.rf[rows]
            def residual(delta):
                parameters[6+satellite]=tau+delta
                prediction,vis=data.predict(parameters,rows,paired)
                return original+(baseline-prediction)*factor,vis
            def cost(delta):
                r,vis=residual(delta)
                return float(np.mean(r*r)) if np.all(vis) else 1e12
            assert np.max(np.abs(residual(0)[0]-original))<1e-9
            delta,value,grid,values=search(cost)
            after,vis=residual(delta)
            before_stats=stats(times,original);after_stats=stats(times,after)
            result=dict(scan=track['scan'],satellite=track['catalog_number'],receiver=track['receiver'],
                        variant=variant,duration_s=float(np.ptp(times)),baseline_timing_s=float(tau),
                        extra_timing_s=delta,total_timing_s=float(tau+delta),
                        boundary_hit=abs(delta)>19.999,all_visible=bool(np.all(vis)),
                        before=before_stats,after=after_stats,time_s=times.tolist(),
                        after_residual_hz=after.tolist(),grid_extra_s=grid.tolist(),grid_mse_hz2=values.tolist())
            results.append(result)
            ax=axes[k,col];ax.scatter(times,original,s=9,alpha=.5,label='Before')
            ax.scatter(times,after,s=9,alpha=.7,label='Timing-only refit')
            ax.axhline(0,color='gray',lw=.7);ax.grid(alpha=.2)
            ax.set_title(f"{track['scan']} · {track['catalog_number']} · {'Original' if variant=='old' else 'Latest available'} TLE\n"
                         f"Δt={delta:+.4f} s; RMS {before_stats['rms_hz']:.1f} → {after_stats['rms_hz']:.1f} Hz")
            ax.set_ylabel('Residual (Hz)')
            print(json.dumps({key:value for key,value in result.items() if key not in
                 ('time_s','after_residual_hz','grid_extra_s','grid_mse_hz2')}),flush=True)
    axes[0,0].legend();axes[-1,0].set_xlabel('Receive time (s)');axes[-1,1].set_xlabel('Receive time (s)')
    fig.suptitle('Each satellite gets an additional ±20 s timing search; RX/RF calibration and GLRT points fixed')
    fig.tight_layout(rect=(0,0,1,.975))
    output=ROOT/'long-track-timing20';output.mkdir(exist_ok=False)
    fig.savefig(output/'comparison.png',dpi=150)
    assert_snapshot_unchanged(hashes)
    (output/'receipt.json').write_text(json.dumps(dict(results=results,source_hashes=hashes,
        scope='Independent timing-only unweighted RMS minimization on each frozen longest track. '
        'Additional +/-20 s around each sealed timing, original and latest archived TLEs separately. '
        'Fixed alias, GLRT peaks, position, RX line, RF coefficient; no extra offsets or polynomial subtraction. '
        'In-sample conditional diagnostic, not a full likelihood or joint calibration refit.'),indent=2,allow_nan=False))


if __name__=='__main__':run()
