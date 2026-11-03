"""Same-input objective cost, not a new localization trial."""
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(HERE.parent/'2026_09_29_unassociated_trend'),str(HERE.parent/'2026_09_29_frequency_contrast')]
import ds7_fast_baseline_adapter as baseline
from ds789_covariance_position import CovariancePosition
from contrast_position import ContrastPosition
from trend_mixture import TrendMixturePosition


def main():
    path=HERE.parent/'2026_09_28_cross_dataset_position/plan.json'
    plan=json.loads(path.read_text());rows=[];sources=[path,Path(__file__)]
    for group in plan['groups']:
        ds=group['dataset_id'];pointpath=ROOT/group['source_point_path'];sources.append(pointpath)
        x=np.array(json.loads(pointpath.read_text())['x'])
        docs=baseline.load_documents({'config':plan['config'],'inputs':group['inputs']})
        for entry in group['inputs']:
            for artifact in entry['artifacts']:
                p=Path(artifact['path']);assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256'];sources.append(p)
        factories={
            'iid':lambda:baseline.JointObjective(docs,plan['config']),
            'shared_scale':lambda:CovariancePosition(docs,plan['config'],0,baseline.Stationary),
            'correlated_10s':lambda:CovariancePosition(docs,plan['config'],10,baseline.Stationary),
            'contrast':lambda:ContrastPosition(docs,plan['config'],baseline.Stationary),
            'q020':lambda:TrendMixturePosition(docs,plan['config'],baseline.Stationary,.2)}
        for name,factory in factories.items():
            original=baseline.baseline.profile
            if name=='iid':baseline.baseline.profile=baseline.profile
            try:
                start=time.perf_counter();model=factory();setup=time.perf_counter()-start
                def evaluate():
                    if name=='iid':return model.value_gradient(x)
                    r=model.evaluate(x,gradient=True,held=False);return -r['score'],-r['gradient']
                expected=evaluate();measure=[]
                for repeat in range(5):
                    start=time.perf_counter();actual=evaluate();elapsed=time.perf_counter()-start
                    np.testing.assert_allclose(actual[0],expected[0],rtol=0,atol=1e-9)
                    np.testing.assert_allclose(actual[1],expected[1],rtol=0,atol=1e-9)
                    assert np.isfinite(actual[0]) and np.all(np.isfinite(actual[1]))
                    measure.append(elapsed)
                rows.append({'dataset':ds,'model':name,'scans':len(docs),
                             'tracks':sum(len(d['tracks']) for d in docs),'parameters':len(x),
                             'setup_s':setup,'objective_gradient_median_s':statistics.median(measure),
                             'repeats_s':measure})
            finally:baseline.baseline.profile=original
    sources.extend(ROOT/p for p in ['tools/ds7_fast_baseline_adapter.py','tools/ds7_baseline_adapter.py','tools/ds789_covariance_position.py'])
    sources.extend(HERE.parent/p for p in ['2026_09_29_unassociated_trend/trend_mixture.py','2026_09_29_frequency_contrast/contrast_position.py'])
    result={'rows':rows,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in set(sources)}}
    with (HERE/'benchmark.json').open('x') as f:json.dump(result,f,indent=2)
    for name in factories:
        selected=[r for r in rows if r['model']==name]
        print(name,'median objective ms',round(1000*statistics.median(r['objective_gradient_median_s'] for r in selected),2),
              'median setup ms',round(1000*statistics.median(r['setup_s'] for r in selected),2))


if __name__=='__main__':main()
