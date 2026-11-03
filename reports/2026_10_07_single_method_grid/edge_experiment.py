"""One controlled follow-up: measured priorities for otherwise unscored edges."""
import concurrent.futures as futures
from dataclasses import asdict
import json
import math
import multiprocessing
from pathlib import Path
import time
import numpy as np
import experiment as base
import edge_grid
from leo.analysis.regional_position_search import distinct_basins, SpatialSearch

HERE=Path(__file__).resolve().parent
OUT=HERE/'edge_priority'

def run():
    OUT.mkdir(exist_ok=False)
    protocol=json.loads((HERE/'protocol.json').read_text())
    for path,expected in protocol['source_hashes'].items():assert base.digest(path)==expected
    base.load();started=time.monotonic()
    baseline=json.loads((HERE/'proposed50_20_5-search.json').read_text())
    scores={tuple(p['point']):p['score'] for p in baseline['points']}
    reproduced,trace=edge_grid.search(lambda points:[scores[tuple(p)] for p in points],edge_policy='legacy-zero')
    assert json.loads(json.dumps(asdict(reproduced)))==baseline['search']
    base.write(OUT/'legacy_reproduction.json',dict(exact=True,**trace))
    sources=[Path(__file__),HERE/'edge_grid.py',HERE/'grid.py',HERE/'experiment.py',HERE/'inputs.json',base.OLD/'bounded_fit.py']
    out=dict(status='running',name='proposed50_20_5_measured_edges',levels_km=[50.,20.,5.],points=[],
        method='V16',relative_sigma_s=1.,slope_half_width_hz_s=60.,budget_points=400,
        source_hashes={str(p):base.digest(p) for p in sources},
        change='Initial unmeasured edge priority inherits nearest measured coarse-center score; all other settings fixed.')
    with futures.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('fork')) as pool:
        def batch(points):
            if time.monotonic()-started>600:raise TimeoutError('bounded follow-up discovery budget')
            rows=list(pool.map(base.score_point,points))
            out['points'].extend({k:r[k] for k in ['point','score','status','elapsed_s','cache_hit']} |
                                 dict(converged=r.get('fit',{}).get('converged')) for r in rows)
            base.write(OUT/'progress.json',out)
            print('EDGE',len(out['points']),flush=True)
            return [r['score'] for r in rows]
        search,meta=edge_grid.search(batch)
        supported=SpatialSearch(tuple(r for r in search.evaluations if r.score<1e100),search.deferred_cells,search.stop_reason)
        basins=distinct_basins(supported,count=3,minimum_separation_km=12.5)
        out.update(search=asdict(search),edge_metadata=meta,basins=[asdict(b) for b in basins],
                   search_elapsed_s=time.monotonic()-started)
        base.write(OUT/'search.json',out)
        tasks=[((b.east_km,b.north_km),max(25.,b.spacing_km/np.sqrt(2))) for b in basins]
        regions={};pending={}
        for task in tasks:
            (e,n),radius=task
            existing=HERE/'regions'/f'{e:g}_{n:g}_{radius:g}.json'
            if existing.exists():regions[task]=json.loads(existing.read_text())
            else:pending[task]=pool.submit(base.refine_region,task)
        regions.update({task:job.result() for task,job in pending.items()})
    candidates=[dict(row,point=task[0],local_radius_km=task[1])
                for task,r in regions.items() for row in r['candidates']]
    out['selections']=[]
    for arm in ('zero-c','fitted-c'):
        eligible=[r for r in candidates if r['arm']==arm and r['feasible']]
        converged=[r for r in eligible if r['converged']]
        key=lambda r:(r['selection_score'],r['point'],r['origin'])
        out['selections'].append(dict(arm=arm,result=min(converged,key=key,default=None),
                                     best_feasible=min(eligible,key=key,default=None)))
    # Reference coordinates remain unavailable to candidate generation and ranking.
    ref=json.loads((HERE/'evaluation.json').read_text());a,b=np.radians([ref['latitude_deg'],ref['longitude_deg']])
    def error(point):
        lat,lon=np.radians(base.coordinates(base.CONTEXT[3],point))
        h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        return float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    for selected in out['selections']:
        for name in ('result','best_feasible'):
            if selected[name] is not None:selected[name]['horizontal_error_m']=error(selected[name]['vector'][:2])
    ranked=sorted(search.evaluations,key=lambda p:(p.score,p.east_km,p.north_km))
    closest=min(enumerate(ranked,1),key=lambda ir:error([ir[1].east_km,ir[1].north_km]))
    out.update(status='complete',elapsed_s=time.monotonic()-started,
               outer10km_points=sum(math.hypot(p.east_km,p.north_km)>=240 for p in search.evaluations),
               closest_evaluated_error_m=error([closest[1].east_km,closest[1].north_km]),
               closest_evaluated_rank=closest[0],
               regions=[dict(point=task[0],radius=task[1],status=r['status'],error=r.get('error'),
                             runs=len(r['runs']),reused=task not in pending) for task,r in regions.items()])
    base.write(OUT/'results.json',out)
    print('COMPLETE',out['elapsed_s'],flush=True)

if __name__=='__main__':run()
