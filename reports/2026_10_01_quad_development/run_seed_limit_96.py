"""Versioned 96-iteration ablation; all other worker behavior unchanged."""
import time
START = time.monotonic()
import argparse
import json
import resource
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from window_inputs import prepare_scan
from acquisition_dot import DotTrackLikelihood, coarse_to_fine
from leo.analysis.localization_search import MemoizedPointScorer
from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_windows import WindowTrackPort, independent_scan_columns, independent_scan_precision
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def prepare_window(unit):
    path = HERE/'selection.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(path.read_text())
    binding = next(r for r in selection['evaluation_units'] if r['unit_id'] == unit)
    scans = [prepare_scan(name) for name in binding['scans']]
    counts = [len(scan.bank.norad_ids) for scan,_,_ in scans]
    columns, precision = independent_scan_columns(counts), independent_scan_precision(counts)
    ports = [WindowTrackPort(p,c,len(precision)) for (_,_,local),c in zip(scans,columns) for p in local]
    return binding, scans, columns, precision, ports


def acquire(scans,deadline):
    local_ports = []
    for scan,height,_ in scans:
        cache = {}
        local_ports.extend(DotTrackLikelihood(t,scan.bank,scan.config,height,4.,geometry_cache=cache)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--seed-limit', type=int, choices=(1, 3), required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    result = dict(unit=args.unit,status='error',fits=[],model='shared_position_independent_scan_nuisances',
                  qualification='Cold development window; hard associations and joint continuous MAP; no GPS in inference.')
    try:
        binding,scans,columns,precision,ports = prepare_window(args.unit)
        size = binding['size']
        deadline = START+90*size-5
        result.update(binding=binding,columns=[c.tolist() for c in columns],precision=precision.tolist(),
            inputs={k:v for scan,_,_ in scans for k,v in scan.inputs.items()},
            height=scans[0][1].input_bindings,observations=[list(p.observation_ids) for p in ports],
            config=dict(prior_radius_km=250,height_m_msl=30.48,seed_limit=args.seed_limit,max_iterations=96,
                        external_limit_s=90*size,internal_limit_s=90*size-5))
        seeds,proposal = acquire(scans,min(START+50*size,deadline-5))
        result['proposal'] = proposal
        for i,seed in enumerate(seeds[:args.seed_limit]):
            if time.monotonic() >= deadline: break
            initial = np.zeros(len(precision));initial[:2] = seed
            started = time.monotonic()
            fit = fit_localization_fast(initial,ports,precision,lambda x: np.linalg.norm(x[:2])<=250,
                max_iterations=96,deadline=deadline,degrees_of_freedom=4.)
            result['fits'].append(dict(seed_index=i,mean=fit.mean.tolist(),objectives=list(fit.objectives),
                converged=fit.converged,reason=fit.reason,iterations=fit.iterations,
                associations=list(fit.associations),seconds=time.monotonic()-started))
        scored = [f for f in result['fits'] if f['objectives']]
        result['best'] = min(scored,key=lambda f:f['objectives'][-1]) if scored else None
        result['status'] = 'converged_local_mode' if result['best'] and result['best']['converged'] else 'unresolved'
        verify_sources(result['inputs'])
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    result['source_sha256'] = {str(Path(m.__file__).resolve()):digest(m.__file__)
        for m in tuple(sys.modules.values()) if getattr(m,'__file__',None)
        and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(wall_seconds=time.monotonic()-START,cpu_seconds=usage.ru_utime+usage.ru_stime)
    with args.output.open('x') as stream: json.dump(result,stream,indent=2,allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k:result[k] for k in ['unit','status','wall_seconds']}),flush=True)


if __name__ == '__main__':
    main()
