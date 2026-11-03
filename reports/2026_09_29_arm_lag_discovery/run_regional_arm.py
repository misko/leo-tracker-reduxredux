"""Saved-RAM restricted search; proposal CPU is reported separately."""
import json
from pathlib import Path
import shlex
import sys
import time
import run_arm

HERE=Path(__file__).resolve().parent
a=run_arm.a

def main():
    out=HERE/'regional-arm-v1';out.mkdir(exist_ok=False)
    binary=HERE/'regional-builds/arm-v1/cohort_regional'
    build=binary.parent/'regional-build.json'
    assert a.sha(binary)==json.loads(build.read_text())['binary_sha256']
    prior=json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())
    old=prior['remote_directory'];remote='/mnt/glrtbench/lag-regional-'+str(int(time.time()))
    a.remote('mkdir '+shlex.quote(remote));a.upload(binary,remote+'/cohort')
    assert a.remote('sha256sum '+remote+'/cohort').split()[0]==a.sha(binary)
    feature={}
    for row in map(json.loads,(HERE/'ds7-32-v1/rows.jsonl').read_text().splitlines()):
        c=row['context'];feature[(c['session_id'],c['visit_index'],row['window'],row['rx'])]=row
    manifest={'complete':False,'selected':prior['selected'],'processed_dwells':0,
         'binary_sha256':a.sha(binary),'build_receipt_sha256':a.sha(build),
         'feature_rows_sha256':a.sha(HERE/'ds7-32-v1/rows.jsonl'),
         'timing_scope':'restricted GLRT search only; measured native proposal cost must be added',
         'remote_directory':remote}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (out/'raw.jsonl').open('x') as stream:
        for i,ctx in enumerate(prior['selected']):
            lines=[]
            for w in range(11):
                for rx in range(2):
                    centers=feature[(ctx['session_id'],ctx['visit_index'],w,rx)]['ranked_epochs']['combined'][:4]
                    epochs=sorted({x for c in centers for x in range(max(0,c-4),min(3333,c+5))})
                    lines.append(str(len(epochs))+' '+' '.join(map(str,epochs)))
            p=out/f'regions-{i}.txt';p.write_text('\n'.join(lines)+'\n');a.upload(p,remote+f'/regions-{i}.txt')
            edge=ctx['target']['edge'];cmd=[remote+'/cohort','2500000',old+'/'+edge+'-exact.c128',
                old+'/'+edge+'-control.c128',old+f'/case-{i}.ci16',remote+f'/regions-{i}.txt']
            raw=a.remote(shlex.join(cmd),timeout=60);(out/f'case-{i}.jsonl').write_text(raw)
            rows=[json.loads(s) for s in raw.splitlines()];assert len(rows)==22
            for row in rows:stream.write(json.dumps({'context':ctx,'native':row})+'\n')
            stream.flush();manifest['processed_dwells']+=1
            print(i,sum(r['timings_ms']['total_cpu'] for r in rows),flush=True)
    manifest.update(complete=True,processed_windows=88,raw_sha256=a.sha(out/'raw.jsonl'))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
