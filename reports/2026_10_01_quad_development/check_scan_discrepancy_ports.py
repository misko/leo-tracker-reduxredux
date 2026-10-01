"""Bounded per-window baseline equivalence and full-objective derivative gate."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from scan_discrepancy_ports import augment_window
from screen_seed_prefix import digest,sealed
from regression_batch import verify_sources

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('unit');args=parser.parse_args()
    assert args.unit in [f'{d}-B01-{s}' for d in ('DS9','DS10','DS11') for s in ('S1','D1','Q')]
    output=HERE/'scan-discrepancy-port-check-v1'/(args.unit+'.json')
    if output.exists():raise FileExistsError(output)
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory=HERE/'independent-v2'/'-'.join(args.unit.split('-')[:2])
        path=directory/(args.unit+'.json');receipt=sealed(path)
        audit_path=directory/'evaluation.json';audit=sealed(audit_path)
        row=next(r for r in audit['rows'] if r['unit']==args.unit)
        assert row['accepted'] and row['receipt_sha256']==digest(path)
        prepared=prepare_window(args.unit)
        assert receipt['binding']==prepared[0]
        assert receipt['precision']==prepared[3].tolist()
        assert receipt['observations']==[list(p.observation_ids) for p in prepared[4]]
        inputs={str(path):digest(path),str(audit_path):digest(audit_path),str(HERE/'selection.json'):digest(HERE/'selection.json')}
        for scan,_,_ in prepared[1]:inputs.update(scan.inputs)
        base=len(prepared[3]);sigma=1.;precision,ports=augment_window(prepared,sigma)
        state=np.r_[receipt['best']['mean'],np.zeros(len(precision)-base)]
        signal_count=0
        for original,p in zip(prepared[4],ports):
            scores=original.score_all(state[:base])
            np.testing.assert_array_equal(p.score_all(state),scores)
            index=int(np.argmax(scores))
            assert p.score_selected(state,index)==original.score_selected(state[:base],index)
            if index<p.candidate_count:
                a=original.predict_selected(state[:base],index);b=p.predict_selected(state,index)
                assert a.eligible==b.eligible
                np.testing.assert_array_equal(a.mean,b.mean)
                np.testing.assert_array_equal(a.covariance,b.covariance)
                np.testing.assert_array_equal(a.jacobian,b.jacobian[:,:base])
                np.testing.assert_array_equal(b.jacobian[:,p.offset_start:p.offset_start+2],a.jacobian[:,:2])
                signal_count+=1
        # Exercise nonzero offsets and prior gradients, without choosing by reference.
        state[base:]=np.tile([.02,-.03],len(prepared[1]))
        gradient=precision*state; assigned=[];active=set()
        for p in ports:
            scores=p.score_all(state);index=int(np.argmax(scores));assigned.append(index)
            if index<p.candidate_count:
                pred=p.predict_selected(state,index);r=p.observation-pred.mean
                solved=np.linalg.solve(pred.covariance,r)
                gradient-=(4+len(r))/(4+float(r@solved))*pred.jacobian.T@solved
                active.update(np.flatnonzero(np.any(pred.jacobian!=0,axis=0)).tolist())
        def objective(x):
            scores=[p.score_all(x) for p in ports]
            assert [int(np.argmax(s)) for s in scores]==assigned,'Association boundary'
            return float(.5*(precision*x)@x-sum(s[i] for s,i in zip(scores,assigned)))
        coordinate_ids=[0,1,*range(base,len(state))]
        coordinate_ids.extend(int(c[2]) for c in prepared[2])
        directions=[]
        for k in coordinate_ids:
            d=np.zeros_like(state);d[k]=1.;directions.append(d)
        rng=np.random.default_rng(1021)
        for _ in range(3):
            d=np.zeros_like(state);d[sorted(active)]=rng.normal(size=len(active));directions.append(d/np.linalg.norm(d))
        errors=[abs((objective(state+step*d)-objective(state-step*d))/(2*step)-gradient@d)
                for step in (.0005,.0001) for d in directions]
        assert max(errors)<.002, max(errors)
        verify_sources(inputs)
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py'
            and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        result=dict(unit=args.unit,tracks=len(ports),signal_tracks_at_zero=signal_count,
            sigma_km=sigma,nonzero_offsets_km=state[base:].tolist(),directions=len(directions),
            maximum_gradient_error=float(max(errors)),inputs=inputs,sources=sources,
            qualification='Prerequisite only: exact zero-offset baseline parity and nonzero-offset full-objective directional derivatives at two steps. No fit or geography score. Hard visibility boundaries remain; no global smoothness claim.')
        output.parent.mkdir(exist_ok=True)
        with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
        output.with_suffix('.sha256').write_text(digest(output)+'\n')
        print(json.dumps({k:result[k] for k in ('unit','tracks','directions','maximum_gradient_error')}),flush=True)


if __name__=='__main__':main()
