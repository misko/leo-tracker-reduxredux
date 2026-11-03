"""Independent A and B position diagnostics; never sum scores across scans."""
import csv
import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from profile_top_2km import Engine, OUT, SEED, point_design, save
from replay import digest


def load_engine(scan, arm):
    engine = Engine(scan, arm)
    # A repeated independent restart may be worse; retain the best converged record.
    engine.cache = {}
    for row in engine.calls:
        key = tuple(np.round([row['east_m'], row['north_m']], 5))
        previous = engine.cache.get(key)
        if previous is None or (row['success'] and not previous['success']) or (
            row['success'] == previous['success'] and row['objective'] < previous['objective']):
            engine.cache[key] = row
    return engine


def independent_case(task):
    scan, arm = task
    started = time.monotonic()
    engine = load_engine(scan, arm)

    def fitted(x, label='independent-search'):
        # Identical convergence criterion and bounded continuation policy for every arm.
        for attempt in range(4):
            row = engine.fit(x, label)
            if row['success']:
                return row
        raise RuntimeError((scan, arm, x, row['attempts']))

    design = point_design()
    cells = []
    for point in design:
        row = fitted(np.array([point['east_m'], point['north_m']]) / 1000, point['label'])
        cells.append(dict(**point, objective=row['objective'], data_nll=row['data_nll'],
                          prior_nll=row['prior_nll'], success=row['success']))
    roof = fitted([0, 0], 'roof')
    for row in cells:
        row['delta_score'] = row['objective'] - roof['objective']
    starts = [np.zeros(2)]
    for point in sorted(cells, key=lambda p: p['objective']):
        x = np.array([point['east_m'], point['north_m']]) / 1000
        if all(np.linalg.norm(x - s) > .4 for s in starts):
            starts.append(x)
        if len(starts) == 4:
            break

    def objective(x):
        # SLSQP can propose infeasible intermediate steps. Project those trials so
        # every expensive position fit remains within the requested 2 km disk.
        radius = np.linalg.norm(x)
        point = x if radius <= 2 else x * (2 / radius)
        row = fitted(point)
        g = np.array(row['gradient_per_km'])
        if radius > 2:
            unit = x / radius
            g = (2 / radius) * (g - unit * (unit @ g)) + 2000 * (radius - 2) * unit
        return row['objective'] + 1000 * max(0., radius - 2) ** 2, g

    trials = []
    for start in starts:
        result = minimize(objective, start, jac=True, method='SLSQP', bounds=[(-2, 2)] * 2,
            constraints=[dict(type='ineq', fun=lambda x: 4 - x @ x, jac=lambda x: -2*x)],
            options=dict(maxiter=35, ftol=1e-7))
        point = result.x * min(1., 2 / max(np.linalg.norm(result.x), 1e-10))
        row = fitted(point)
        trials.append(dict(start_km=start, point_km=point, objective=row['objective'],
            gradient_per_km=row['gradient_per_km'], success=bool(result.success),
            message=str(result.message), iterations=int(result.nit)))
    best_trial = min(trials, key=lambda r: r['objective'])
    point = np.array(best_trial['point_km'])
    best = fitted(point)
    before = best['objective']
    restart = engine.fit(point, 'independent-best-roof-restart', force_start=roof['vector'])
    if not restart['success']:
        restart = fitted(point, 'independent-best-roof-restart-continue')
    best = engine.cache[tuple(np.round(point * 1000, 5))]
    neighbors = []
    for j in range(8):
        x = point + .025 * np.array([np.sin(j*np.pi/4), np.cos(j*np.pi/4)])
        if np.linalg.norm(x) <= 2 + 1e-9:
            row = fitted(x, 'independent-neighbor-25m')
            neighbors.append(dict(point_km=x, objective=row['objective'],
                                  delta_from_best=row['objective'] - best['objective']))
    lookup = {(p['east_m'], p['north_m']): p for p in cells}
    derivatives = [dict(step_m=h, gradient_per_100m=[
        (lookup[h, 0.]['objective'] - lookup[-h, 0.]['objective']) / (2*h) * 100,
        (lookup[0., h]['objective'] - lookup[0., -h]['objective']) / (2*h) * 100])
        for h in (50., 100.)]
    result = dict(scan=scan, arm=arm, cells=cells, roof=roof, best=best, trials=trials,
        best_sampled=min(cells, key=lambda r: r['objective']),
        east_m=point[0]*1000, north_m=point[1]*1000, distance_m=np.linalg.norm(point)*1000,
        delta_score=best['objective'] - roof['objective'],
        delta_data_nll=best['data_nll'] - roof['data_nll'],
        delta_prior_nll=best['prior_nll'] - roof['prior_nll'],
        boundary_limited=bool(np.linalg.norm(point) > 1.999),
        score_change_after_roof_restart=best['objective'] - before,
        neighbors_25m=neighbors, derivatives=derivatives, elapsed_s=time.monotonic() - started)
    save(OUT/f'independent-{scan}-{arm}.json', result)
    return result


def render(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    limit=max(abs(p['delta_score']) for r in results for p in r['cells'])
    fig, axes=plt.subplots(2, 2, figsize=(12, 12), sharex=True, sharey=True)
    for r in results:
        i=('fitted-c', 'zero-c').index(r['arm']); j=('A', 'B').index(r['scan']); ax=axes[i,j]
        cells=r['cells'];g=np.array(r['derivatives'][0]['gradient_per_100m'])
        im=ax.scatter([p['east_m']/1000 for p in cells], [p['north_m']/1000 for p in cells],
            c=[p['delta_score'] for p in cells], cmap='RdBu_r', vmin=-limit, vmax=limit,
            s=43, edgecolors='.4')
        ax.plot(0, 0, 'k+', ms=13, mew=2, label='Known roof')
        ax.add_patch(plt.Circle((0,0),2,fill=False,ls=':',color='.5'))
        ax.arrow(0,0,*(-g/np.linalg.norm(g)*.5), head_width=.10, width=.012,
                 color='black', length_includes_head=True)
        point=np.array([r['east_m'],r['north_m']])/1000
        ax.plot(*point,'*',ms=18,c='gold',mec='black',label='Best independent local search')
        ax.annotate(f"{r['distance_m']:.0f} m from roof\nΔscore {r['delta_score']:+.2f}" +
                    ('\nBoundary-limited' if r['boundary_limited'] else ''),point,
                    xytext=(7,14),textcoords='offset points',fontsize=9)
        ax.set_title(f"Scan {r['scan']} · {r['arm']}\nGradient / 100 m: E {g[0]:+.2f}, N {g[1]:+.2f}",fontsize=12)
        ax.set(xlim=(-2.25,2.25),ylim=(-2.25,2.25),xlabel='East of roof (km)',ylabel='North of roof (km)')
        ax.set_aspect('equal');ax.grid(alpha=.15);ax.legend(fontsize=8,loc='upper left')
    fig.subplots_adjust(left=.08,right=.87,bottom=.14,top=.85,hspace=.27,wspace=.22)
    cax=fig.add_axes([.91,.22,.02,.54]);fig.colorbar(im,cax=cax,label='Profile score − own roof score (lower is better)')
    fig.suptitle('DS13 · independent scan position tests within 2 km',fontsize=18,y=.97)
    fig.text(.5,.915,'A and B fitted separately: no shared position, no summed score.\nSame top-response observations and satellite sets in both RF arms.',ha='center',fontsize=11)
    fig.text(.5,.045,'48 reproducible random locations + 16 boundary probes + roof and ±50/100 m cardinal probes per panel.\nSaved receiver baseline fixed; additional RX offsets/drifts, RF coefficient and satellite timing refitted at every site.\nFour-start local search and 25 m neighborhood checks; not a global-minimum certificate.',ha='center',fontsize=10)
    fig.savefig(OUT/'independent-position-profile-2km.png',dpi=170);plt.close(fig)


def main():
    tasks=[(s,a) for s in ('A','B') for a in ('fitted-c','zero-c')]
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('fork')) as pool:
        results=list(pool.map(independent_case,tasks))
    save(OUT/'independent-summary.json',dict(cases=results,seed=SEED,
        scope='Independent scan positions and nuisance parameters. All top-response windows retained, including unassigned.',
        score='Per-scan finite-set negative log likelihood plus Gaussian timing priors; not discrete greedy coverage score.',
        source_hashes={str(p):digest(p) for p in (Path(__file__),Path(__file__).with_name('profile_top_2km.py'),
            OUT/'A-profile-input.json',OUT/'B-profile-input.json',OUT/'A-profile-input.npz',OUT/'B-profile-input.npz')}))
    rows=[dict(scan=r['scan'],arm=r['arm'],**p) for r in results for p in r['cells']]
    with (OUT/'independent-scores.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    render(results)


if __name__=='__main__':
    main()
