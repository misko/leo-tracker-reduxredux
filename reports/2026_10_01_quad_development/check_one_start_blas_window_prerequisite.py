"""Multi-scan track, aggregate score and full proposal equivalence gate."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from acquisition_dot import DotTrackLikelihood
from acquisition_blas import BlasTrackLikelihood
from acquire_blas import acquire_blas
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit',choices=[d+'-B01-'+s for d in ('DS9','DS10','DS11') for s in ('D1','Q')]);args=parser.parse_args()
    unit=args.unit;output=HERE/'one-start-blas-window-prerequisite-v1'/(unit+'.json')
    if output.exists():raise FileExistsError(output)
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        parent=HERE/'independent-v2'/unit.rsplit('-',1)[0]/(unit+'.json');original=sealed(parent)
        verify_sources(original['source_sha256']);verify_sources(original['inputs'])
        binding,scans,_,_,_=prepare_window(unit)
        assert binding==original['binding'] and len(scans)==binding['size']
        points=np.vstack((np.array([[0,0],[100,0],[-100,0],[0,100],[0,-100],[176,176],[-176,176],[176,-176],[-176,-176]]),np.asarray(original['proposal']['seeds'])))
        assert np.all(np.linalg.norm(points,axis=1)<=250)
        maximum=0.;tracks=0;total_old=np.zeros(len(points));total_new=np.zeros(len(points))
        for scan,height,_ in scans:
            cache_old={};cache_new={}
            for _,track in scan.tracks:
                old=DotTrackLikelihood(track,scan.bank,scan.config,height,4.,geometry_cache=cache_old)
                new=BlasTrackLikelihood(track,scan.bank,scan.config,height,4.,geometry_cache=cache_new)
                a=old(points,np.empty((1,0)));b=new(points,np.empty((1,0)))
                np.testing.assert_array_equal(np.isfinite(a),np.isfinite(b))
                np.testing.assert_array_equal(np.isneginf(a),np.isneginf(b))
                assert not np.isnan(a).any() and not np.isnan(b).any()
                error=float(np.max(np.abs(a[np.isfinite(a)]-b[np.isfinite(b)])))
                assert error<1e-6;maximum=max(maximum,error);tracks+=1
                for values,total in ((a,total_old),(b,total_new)):
                    top=values[:,0,:].max(axis=1)
                    total += top+np.log(np.exp(values[:,0,:]-top[:,None]).sum(axis=1))
        aggregate_error=float(np.max(np.abs(total_old-total_new)))
        assert aggregate_error<1e-6
        started=time.monotonic();seeds,proposal=acquire_blas(scans,started+50*binding['size'])
        elapsed=time.monotonic()-started
        checks={key:proposal[key]==original['proposal'][key] for key in ('seeds','requested','unique_points','spacing')}
        checks['scores']=bool(np.allclose(proposal['scores'],original['proposal']['scores'],rtol=0,atol=1e-6))
        assert all(checks.values()),checks
        inputs={str(parent):digest(parent),**original['inputs']}
        for _,height,_ in scans:
            inputs[height.input_bindings['grid_path']]=height.input_bindings['grid_sha256']
        verify_sources(inputs)
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'
            and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        for name in ('run_one_start_blas.py','test_one_start_blas_wrapper.py','run_seed_limit.py','ONE_START_BLAS_WINDOW_PLAN.md'):
            sources[str(HERE/name)]=digest(HERE/name)
        result=dict(unit=unit,tracks=tracks,points_km=points.tolist(),maximum_score_error=maximum,aggregate_score_error=aggregate_error,
            proposal_checks=checks,optimized_proposal_seconds=elapsed,inputs=inputs,sources=sources,
            qualification='No fit or reference scoring. All-track finite/visibility masks and scores plus summed marginalized acquisition scores at fixed prior points plus original acquired seeds; full BLAS acquisition compared with saved original proposal. No runtime speedup inferred from one acquisition measurement.')
        output.parent.mkdir(exist_ok=True)
        with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps({k:result[k] for k in ('unit','tracks','maximum_score_error','aggregate_score_error','proposal_checks','optimized_proposal_seconds')}),flush=True)


if __name__=='__main__':main()
