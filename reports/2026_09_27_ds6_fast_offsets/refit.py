"""Matched three-scan refit with converged offsets in both likelihood arms."""
import argparse
import importlib.util
import json
from pathlib import Path
import solver
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('continuous',ROOT/'2026_09_27_ds6_continuous_phase/run.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def score(residual,mask,sigma=100.):
    a,b,_=solver.scores(residual,mask,sigma);return a,b
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['cfo_only','phase'],required=True);args=ap.parse_args()
    output=HERE/'refit';output.mkdir(exist_ok=True);source=ROOT/'2026_09_27_ds6_continuous_phase/protocol.json';p=json.loads(source.read_text());p['stationary_solver_sha256']=old.joint.sha(HERE/'solver.py');p['original_protocol_sha256']=old.joint.sha(source);p['offset_policy']='Bracket-checked multistart stationary solver; same observations, candidate sets and two starts; train only'
    pp=output/'protocol.json'
    if pp.exists():assert json.loads(pp.read_text())==p
    else:pp.write_text(json.dumps(p,indent=2)+'\n')
    old.HERE=output;old.geo.pair.u.robust_scores=score
    old.run(args.arm)
