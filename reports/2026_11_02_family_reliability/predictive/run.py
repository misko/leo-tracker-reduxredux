"""Bounded four-worker report adapter, writes each completed job immediately."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import multiprocessing
import os
import time
import traceback
import predictive as p
from algo07_science import engine as e

CONTEXT=None


def job(spec):
    d,z=CONTEXT;arm,fold,variant,scale,norad,part=spec
    try:return p.evaluate_context(d,z,norad,scale,variant,dict(part,arm=arm))
    except Exception:return dict(arm=arm,fold=fold,solver=variant,SD_scale=scale,norad=norad,error=traceback.format_exc())


def main():
    global CONTEXT
    parser=argparse.ArgumentParser();parser.add_argument('--cases',nargs='+',default=['DS26-0309','DS26-0070']);args=parser.parse_args()
    p.family.configure();began=time.monotonic()
    for case in args.cases:
        d,z,replay=e.load_case(case);norad,ranked=p.family.select_family(d,z)
        parts,digest=p.seal(case,d,z);CONTEXT=(d,z)
        p.write(p.ROOT/(case+'_inventory.json'),dict(case=case,norad=norad,RF_ranked=ranked,replay=replay,
            protocol_sha256=digest,source_sha256={str(f):p.hashlib.sha256(f.read_bytes()).hexdigest() for f in
            [p.ROOT/'predictive.py',p.ROOT.parent/'family/prototype.py',p.ROOT.parent/'solver/solver.py']}))
        jobs=[(arm,part['fold'],variant,scale,norad,part) for arm in e.ARMS for part in parts for variant,scale in p.MODELS]
        outputs=[]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
            futures={pool.submit(job,spec):spec for spec in jobs}
            for future in as_completed(futures):
                out=future.result();outputs.append(out)
                label=f"{case}_{out['arm']}_f{out['fold']}_{out['solver']}_SD{out['SD_scale']:g}"
                p.write(p.ROOT/(label+'.json'),out)
                print(label,'error' if 'error' in out else
                    dict(score=out['scores']['all']['negative_twice_log_density'],other=out['scores']['other']['negative_twice_log_density'],
                         closed=out['phase_closed'],seconds=round(out['seconds'],2)),flush=True)
        p.write(p.ROOT/(case+'_results.json'),dict(case=case,protocol_sha256=digest,rows=outputs,seconds=time.monotonic()-began))


if __name__=='__main__':main()
