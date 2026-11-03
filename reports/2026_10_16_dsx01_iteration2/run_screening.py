"""Apply the same frozen generic screening to every DSX01 recording."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_10_16_dsx01_models'))
from common import load_context,save_json
from bank_expansion import regional_bank
from candidate_screen import screen


def run(sid):
    path=HERE/f'candidate_screen_{sid}.json'
    if path.exists():
        return dict(source=sid,status='existing')
    begun=time.monotonic()
    ctx=load_context(sid)
    bank,authority=regional_bank(ctx,return_receipt=True)
    ids,diagnostics=screen(ctx,bank,max_additions=8,max_seconds=60)
    sources={str(p.resolve()):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
             for p in [HERE/'candidate_screen.py',HERE/'bank_expansion.py',
                       HERE.parent/'2026_10_16_dsx01_models/common.py']}
    save_json(path,dict(label=sid,selected_ids=ids,authority=authority,diagnostics=diagnostics,
        sources=sources,elapsed_including_preparation_seconds=time.monotonic()-begun,
        baseline_replay_objectives=2,screen_objective_calls=0,localization_fits=0))
    return dict(source=sid,selected_ids=ids,screen_state=diagnostics['state'],seconds=time.monotonic()-begun)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sources',nargs='+',default=['S01','S02','S03','S04','S05'])
    p.add_argument('--workers',type=int,default=3)
    args=p.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in as_completed([pool.submit(run,s) for s in args.sources]):
            print(json.dumps(result.result()),flush=True)


if __name__=='__main__':
    main()
