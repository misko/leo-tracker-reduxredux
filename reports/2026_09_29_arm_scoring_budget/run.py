"""Measure final scoring with original coordinates supplied by an oracle.

This deliberately excludes discovery cost. Positive-only timings are a
retrospective subset of separately timed calls, not an implemented policy.
"""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as transport

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data): p.write_text(json.dumps(data,indent=2)+'\n')

def main():
    source=HERE.parent/'2026_09_28_arm_boundary_fallback/builds/arm-v1'
    output=HERE/(sys.argv[1] if len(sys.argv)>1 else 'run-v2'); output.mkdir(exist_ok=False)
    build=output/'build'; shutil.copytree(source,build)
    shutil.copyfile(HERE/'probe.c',build/'probe.c')
    receipt=json.loads((source/'build.json').read_text())
    command=receipt['commands'][0]
    command=[x.replace(str(Path(command[command.index('-I')+1]).parents[1]),str(build))
             if isinstance(x,str) else x for x in command]
    # Use the qualified compiler flags, includes and libraries, with one
    # translation unit including the frozen full_search.c implementation.
    command=[x for x in command if not x.endswith('/full_search.c')]
    command=[str(build/'probe.c') if x.endswith('/probe_main.c') else x for x in command]
    command[-1]=str(build/'probe')
    if '--direct' in sys.argv: command.insert(1,'-DDIRECT_CI16')
    if '--shared' in sys.argv: command.insert(1,'-DSHARED_DWELL')
    subprocess.run(command,check=True,capture_output=True)
    write(output/'build-receipt.json',{'command':command,'binary_sha256':sha(build/'probe'),
          'source_sha256':{str(p.relative_to(build)):sha(p) for p in build.rglob('*') if p.suffix in ('.c','.h')}})
    manifest=json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())
    baseline=transport.baseline()
    remote='/mnt/glrtbench/scoring-budget-'+str(int(time.time()))
    transport.remote('mkdir '+shlex.quote(remote))
    transport.upload(build/'probe',remote+'/probe')
    assert transport.remote('sha256sum '+remote+'/probe').split()[0]==sha(build/'probe')
    old=manifest['remote_directory']
    results=[]
    for i,ctx in enumerate(manifest['selected']):
        probes=baseline[(ctx['session_id'],ctx['visit_index'])]
        seeds=output/f'seeds-{i}.txt'
        rows=[]
        for window in range(11):
            for rx in range(2):
                candidates=probes[(rx,window)]['candidates']
                assert len(candidates)==8
                for rank,c in enumerate(candidates):
                    rows.append(f"{window} {rx} {rank} {c['epoch_sample']} {c['acquired_cfo_hz']:.17g}\n")
        seeds.write_text(''.join(rows)); transport.upload(seeds,remote+f'/seeds-{i}.txt')
        edge=ctx['target']['edge']
        # Bind reused CI16 bytes to the original local NPY payload.
        import numpy as np
        data=np.load(transport.INPUTS/ctx['file'])
        payload_hash=hashlib.sha256(data.tobytes()).hexdigest()
        assert transport.remote(f'sha256sum {old}/case-{i}.ci16').split()[0]==payload_hash
        for rep in range(3):
            args=[remote+'/probe','2500000',old+'/'+edge+'-exact.c128',
                  old+'/'+edge+'-control.c128',old+f'/case-{i}.ci16',remote+f'/seeds-{i}.txt']
            raw=transport.remote(shlex.join(args),timeout=30)
            (output/f'case-{i}-r{rep}.jsonl').write_text(raw)
            native=[json.loads(line) for line in raw.splitlines()]
            assert len(native)==176
            positive=0; positive_ms=0.; all_ms=0.; ingestion={}; unique=set()
            for row in native:
                key=(row['window'],row['rx'],row['rank']); assert key not in unique; unique.add(key)
                c=probes[(row['rx'],row['window'])]['candidates'][row['rank']]
                assert row['epoch']==c['epoch_sample']
                assert abs(row['exact']-c['exact_score'])<=2e-9
                assert abs(row['control']-c['control_score'])<=2e-9
                assert abs(row['tracking_cfo']-c['tracking_cfo_hz'])<=2e-6
                assert row['cpu_ms']>=0
                all_ms+=row['cpu_ms']; ingestion[key[:2]]=row['window_ingest_ms']
                if c['margin']>=.025:
                    positive+=1; positive_ms+=row['cpu_ms']
            results.append({'case':i,'repeat':rep,'context':ctx,'windows':22,'candidates':176,
                 'positive_candidates':positive,'all_scoring_ms':all_ms,
                 'oracle_positive_scoring_ms':positive_ms,
                 'ingest_ms':sum(ingestion.values())+native[0].get('dwell_convert_ms',0),
                 'baseline_score_parity':True,'ci16_sha256':payload_hash})
            write(output/'partial.json',results)
            print(i,rep,positive,round(all_ms,3),round(positive_ms,3),flush=True)
    write(output/'summary.json',{'complete':True,'oracle_diagnostic_only':True,'remote':remote,
         'baseline_sha256':sha(transport.BASELINE),'rows':results,
         'mean_all_scoring_ms':sum(r['all_scoring_ms'] for r in results)/len(results),
         'mean_oracle_positive_scoring_ms':sum(r['oracle_positive_scoring_ms'] for r in results)/len(results),
         'mean_ingest_ms':sum(r['ingest_ms'] for r in results)/len(results)})

if __name__=='__main__':main()
