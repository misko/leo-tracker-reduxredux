"""All-rate original-coordinate parity; does not evaluate discovery recall."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def main():
    variant=sys.argv[1] if len(sys.argv)>1 else 'explicit-ci16-v2'
    out=HERE/(sys.argv[2] if len(sys.argv)>2 else 'host704-v4');out.mkdir(exist_ok=False)
    build=HERE/variant/'build'
    receipt=json.loads((HERE/variant/'build-receipt.json').read_text())
    cmd=[x for x in receipt['command'] if x not in ('-mcpu=cortex-a9','-mfpu=neon',
        '-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-Werror')]
    cmd[0]='gcc';cmd[-1]=str(out/'probe')
    cmd.insert(1,'-D_POSIX_C_SOURCE=200809L')
    cmd=['-lfftw3f' if x.endswith('/libfftw3f.a') else x for x in cmd]
    compile_result=subprocess.run(cmd,check=True,capture_output=True,text=True)
    (out/'compiler.stderr').write_text(compile_result.stderr)
    (out/'build.json').write_text(json.dumps({'command':cmd,'binary_sha256':a.sha(out/'probe'),
        'source_receipt_sha256':a.sha(HERE/variant/'build-receipt.json')},indent=2)+'\n')
    base=a.baseline()
    contexts=json.loads((a.INPUTS/'inputs.json').read_text())
    if isinstance(contexts,dict): contexts=contexts.get('rows',contexts.get('inputs'))
    assert isinstance(contexts,list) and len(contexts)==704
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    templates={(c['context']['rate_hz'],c['context']['target']['edge']):c['templates'] for c in oracle['cases']}
    def case(ctx):
        directory=out/str(ctx['ordinal']);directory.mkdir()
        source=a.INPUTS/ctx['file'];assert a.sha(source)==ctx['sha256']
        iq=np.load(source,allow_pickle=False);path=directory/'input.ci16';iq.tofile(path)
        probes=base[(ctx['session_id'],ctx['visit_index'])]
        seeds=directory/'seeds.txt'; lines=[]
        for w in range(11):
            for rx in range(2):
                assert len(probes[(rx,w)]['candidates'])==8
                for k,c in enumerate(probes[(rx,w)]['candidates']):
                    lines.append(f"{w} {rx} {k} {c['epoch_sample']} {c['acquired_cfo_hz']:.17g}\n")
        seeds.write_text(''.join(lines))
        ts=templates[(ctx['rate_hz'],ctx['target']['edge'])]
        for t in ts.values():assert a.sha(a.ORACLE/t['file'])==t['sha256']
        args=[str(out/'probe'),str(ctx['rate_hz']),str(a.ORACLE/ts['exact']['file']),
              str(a.ORACLE/ts['control']['file']),str(path),str(seeds)]
        result=subprocess.run(args,check=True,text=True,capture_output=True)
        assert not result.stderr
        (directory/'raw.jsonl').write_text(result.stdout)
        rows=[json.loads(x) for x in result.stdout.splitlines()];assert len(rows)==176
        seen=set(); positive=0;score_delta=0.;cfo_delta=0.
        for r in rows:
            key=r['window'],r['rx'],r['rank'];assert key not in seen;seen.add(key)
            c=probes[(r['rx'],r['window'])]['candidates'][r['rank']]
            assert r['epoch']==c['epoch_sample'] and r['cfo']==c['acquired_cfo_hz']
            score_delta=max(score_delta,abs(r['exact']-c['exact_score']),abs(r['control']-c['control_score']))
            cfo_delta=max(cfo_delta,abs(r['tracking_cfo']-c['tracking_cfo_hz']))
            assert (r['exact']-r['control']>=.025)==(c['margin']>=.025)
            positive+=c['margin']>=.025
        assert score_delta<2e-9 and cfo_delta<2e-6
        # Generated local payload only, not a source corpus path.
        path.unlink()
        return {'context':ctx,'windows':22,'candidate_entries':176,'positive_entries':positive,
                'max_score_delta':score_delta,'max_cfo_delta_hz':cfo_delta,
                'raw_sha256':a.sha(directory/'raw.jsonl')}
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(case,contexts):
            rows.append(result)
            if len(rows)%32==0:print('verified',len(rows),flush=True)
    summary={'complete':True,'oracle_seeded':True,'baseline_sha256':a.sha(a.BASELINE),
        'input_manifest_sha256':a.sha(a.INPUTS/'inputs.json'),'rows':rows,
        'windows':sum(r['windows'] for r in rows),'candidate_entries':sum(r['candidate_entries'] for r in rows),
        'positive_entries':sum(r['positive_entries'] for r in rows),
        'max_score_delta':max(r['max_score_delta'] for r in rows),
        'max_cfo_delta_hz':max(r['max_cfo_delta_hz'] for r in rows)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print({k:v for k,v in summary.items() if k!='rows'},flush=True)

if __name__=='__main__':main()
