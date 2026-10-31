"""Inspect causal model support and independent curve witnesses, without GPS."""
import concurrent.futures
from pathlib import Path
import sys
from run_trials import STUDY, RELEASE, targets, stage, write

def one(t):
    output=STUDY/t['case']/'control-witnesses.json'
    cmd=[sys.executable,str(RELEASE/'tools/diagnose_graph_residual_witnesses.py'),
         '--inventory',t['inventory'],'--source',str(Path(t['recovery'])/t['track_id']/'trial'),
         '--output',str(output),'--shared-family','--control']
    receipt=stage(cmd,STUDY/t['case']/'control-witnesses.log',180)
    write(STUDY/t['case']/'control-witnesses-receipt.json',receipt)
    return receipt

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        print(list(pool.map(one,targets())))
