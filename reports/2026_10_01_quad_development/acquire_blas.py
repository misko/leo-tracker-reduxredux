"""Same adaptive acquisition policy with numerically equivalent matrix products."""
import time
import numpy as np
from acquisition_blas import BlasTrackLikelihood
from acquisition_dot import coarse_to_fine
from leo.analysis.localization_search import MemoizedPointScorer

def acquire_blas(scans,deadline):
    local_ports = []
    for scan,height,_ in scans:
        cache = {}
        local_ports.extend(BlasTrackLikelihood(t,scan.bank,scan.config,height,4.,geometry_cache=cache)
                           for _,t in scan.tracks)
    def score(points):
        total = np.zeros(len(points))
        for begin in range(0,len(points),32):
            chunk = points[begin:begin+32]
            for port in local_ports:
                if time.monotonic() >= deadline:
                    raise TimeoutError('window acquisition deadline')
                values = port(chunk,np.empty((1,0)))[:,0,:]
                maximum = values.max(axis=1)
                total[begin:begin+len(chunk)] += maximum+np.log(np.exp(values-maximum[:,None]).sum(axis=1))
        return total
    cached = MemoizedPointScorer(score)
    seeds,scores,requested,spacing = coarse_to_fine(cached)
    return seeds,dict(seeds=seeds.tolist(),scores=scores.tolist(),requested=requested,
                      unique_points=cached.evaluated_points,spacing=spacing)
