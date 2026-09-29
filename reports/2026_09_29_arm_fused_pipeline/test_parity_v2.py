#!/usr/bin/env python3
"""Compare fused output with the two frozen executables on one dwell/rate."""
import argparse,json,subprocess,tempfile
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ORACLE=Path('/var/tmp/leo-arm-full-search-oracle-allrates')
INPUTS=Path('/var/tmp/leo-ds7-large-arm-20260928')
def rows(cmd):
    p=subprocess.run([str(x) for x in cmd],text=True,capture_output=True,check=True,timeout=120)
    assert not p.stderr;return [json.loads(x) for x in p.stdout.splitlines()]
def region_epochs(centers,n):return sorted({v for c in centers[:4] for v in range(max(0,c-2),min(n,c+3))})
def science(row):return {'receiver_id':row['receiver_id'],'probe_index':row['probe_index'],'candidates':row['candidates']}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--all-rates',action='store_true');args=ap.parse_args()
    oracle=json.loads((ORACLE/'oracle.json').read_text()); cases=oracle['cases'] if args.all_rates else oracle['cases'][:1]
    fused=HERE/'builds-v2/host/fused_pipeline_v2_host'
    proposal=HERE.parent/'2026_09_29_arm_neon_proposal/builds/host/proposal_probe_host'
    search=HERE.parent/'2026_09_29_arm_final_reuse/builds/host/cohort_final_reuse_f2_rawcondition_host'
    checked=[]
    for case in cases:
        ctx=case['context'];rate=ctx['rate_hz'];n=round(rate/750);exact=ORACLE/case['templates']['exact']['file'];control=ORACLE/case['templates']['control']['file']
        with tempfile.TemporaryDirectory(prefix='fused-parity-') as td:
            td=Path(td);raw=td/'input.ci16';np.load(INPUTS/ctx['file'],allow_pickle=False).tofile(raw)
            proposed=rows([proposal,rate,exact,raw,'--combined-only']);assert len(proposed)==22
            regions=[]
            for row in proposed:
                epochs=region_epochs(row['top4']['combined'],n);regions.append(str(len(epochs))+' '+' '.join(map(str,epochs)))
            region=td/'regions.txt';region.write_text('\n'.join(regions)+'\n')
            separate=rows([search,rate,exact,control,raw,region]);combined=rows([fused,rate,exact,control,raw])
            assert len(separate)==len(combined)==22
            assert [science(x) for x in separate]==[science(x) for x in combined]
            assert all(x['candidate_count']==8 for x in combined)
            assert all(x['timings_ms']['fused_total']>=x['timings_ms']['stage_sum'] for x in combined)
            checked.append({'rate_hz':rate,'windows':22,'candidates':sum(x['candidate_count'] for x in combined),'exact_parity':True,
                'proposal_cpu_ms':sum(x['timings_ms']['proposal'] for x in combined),
                'search_cpu_ms':sum(x['timings_ms']['total_cpu'] for x in combined),
                'stage_sum_cpu_ms':sum(x['timings_ms']['stage_sum'] for x in combined),
                'fused_cpu_ms':sum(x['timings_ms']['fused_total'] for x in combined),
                'outer_overhead_cpu_ms':sum(x['timings_ms']['fused_total']-x['timings_ms']['stage_sum'] for x in combined)})
    print(json.dumps({'schema':'arm-fused-pipeline-parity/v1','cases':checked},indent=2))
if __name__=='__main__':main()
