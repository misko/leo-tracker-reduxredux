import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main(panel,height):
    started=time.monotonic()
    spec=importlib.util.spec_from_file_location('budget',HERE.parent/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);helper=budget.helper
    sys.path.insert(0,str(HERE.parent/'2026_09_29_height_sensitivity'))
    from height_model import HeightStationary
    plan=json.loads((HERE/'plan.json').read_text())
    for name,h in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    assert height in (0.,20.,40.)
    wanted=plan['panels'][panel]
    rows={r['session_id']:r for r in plan['captures']}
    inputs=[];hashes={}
    for sid in wanted:
        path=HERE/'exports'/rows[sid]['unit_id']/'validated.json'
        raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest()
        result=json.loads(raw);assert result['mint_analysis_match'] and result['input']['session_id']==sid
        inputs.append(result['input'])
        for a in result['input']['artifacts']:
            assert 'sha256:'+hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256']
            hashes[a['path']]=a['sha256'].removeprefix('sha256:')
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=inputs))
    assert [d['session_id'] for d in docs]==wanted
    config=dict(plan['config'],receiver_height_m=height)
    factory=helper.baseline.Stationary if height==0 else HeightStationary
    def model(dd):return helper.TrendMixturePosition(dd,config,factory,.2)
    m=model(docs);singles=[model([d]) for d in docs];grid=np.array(config['timing_grid_s'])
    outdir=HERE/'fits'/f'{panel}_h{int(height)}';outdir.mkdir(parents=True,exist_ok=True)
    for p in [HERE/'plan.json',HERE/'fit_panel.py',HERE.parent/'2026_09_29_height_sensitivity/height_model.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    starts=[]
    for family in ['cold','timing_grid']:
        for east in [-2.,0.,2.]:
            path=outdir/f'{family}_{int(east)}.json'
            if path.exists():
                saved=json.loads(path.read_text());assert saved['hashes']==hashes
                starts.append(saved['fit']);continue
            x=np.zeros(2+len(docs));x[0]=east
            if family=='timing_grid':
                for i,one in enumerate(singles):
                    if height==0:
                        scores,_=budget.training_scores(one,x[:2],grid)
                    else:
                        scores=np.array([one.evaluate([east,0.,tau],gradient=False)['score'] for tau in grid])
                    x[i+2]=grid[int(np.argmax(scores))]
            result=dict(helper.fit_model(m,x),initial=x.tolist(),family=family)
            with path.open('x') as out:json.dump(dict(fit=result,hashes=hashes),out,indent=2,allow_nan=False)
            starts.append(result)
            print(panel,height,family,east,result['qualified'],flush=True)
    valid=[r for r in starts if r['qualified']]
    best=dict(max(valid,key=lambda r:r['score'])) if valid else None
    if best:
        scored=m.evaluate(best['x'],gradient=False,held=True)
        best.update(estimate_deg=list(m.models[0].coordinates(best['x'][:3])),held_score=sum(r['held_log_score'] for r in scored['rows']))
    result=dict(panel=panel,height_m=height,sessions=wanted,starts=starts,selected=best,
                tracks=sum(len(d['tracks']) for d in docs),observations=sum(len(t['y']) for d in docs for t in d['tracks']),hashes=hashes,elapsed_seconds=time.monotonic()-started)
    with (outdir/'result.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print('Completed',panel,height,best is not None,flush=True)


if __name__=='__main__':main(sys.argv[1],float(sys.argv[2]))
