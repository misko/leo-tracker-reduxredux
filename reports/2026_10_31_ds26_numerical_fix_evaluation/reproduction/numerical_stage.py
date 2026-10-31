"""Opt-in runpy bootstrap for one existing frozen ALGO03 stage, not a batch launcher."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

from numerical_helper import patched_stages


def run_stage(script,arguments,*,reference_limit_s,centered_lbfgsb,receipt):
    script=Path(script).resolve();receipt=Path(receipt)
    if not script.is_file():raise ValueError('existing frozen stage script required')
    if receipt.exists():raise FileExistsError(receipt)
    began=time.monotonic();prior_argv=sys.argv;prior_path=sys.path.copy();state=None
    try:
        sys.argv=[str(script),*map(str,arguments)];sys.path.insert(0,str(script.parent))
        with patched_stages(reference_limit_s=reference_limit_s,centered_lbfgsb=centered_lbfgsb) as state:
            return runpy.run_path(str(script),run_name='__main__')
    except BaseException as exc:
        if state is not None:state['stage_exception']=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        sys.argv=prior_argv;sys.path[:]=prior_path
        if state is not None:
            state.update(script=str(script),arguments=list(map(str,arguments)),seconds=time.monotonic()-began,
                script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                bootstrap_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            receipt.parent.mkdir(parents=True,exist_ok=True)
            with receipt.open('x') as stream:json.dump(state,stream,indent=2,allow_nan=False);stream.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-limit-s',type=int,choices=(15,30),required=True)
    p.add_argument('--centered-lbfgsb',action='store_true');p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('script',type=Path);p.add_argument('arguments',nargs=argparse.REMAINDER);a=p.parse_args()
    run_stage(a.script,a.arguments,reference_limit_s=a.reference_limit_s,centered_lbfgsb=a.centered_lbfgsb,receipt=a.receipt)
