"""Native proposal cost on four saved ARM dwells, never a GLRT benchmark."""
import json
from pathlib import Path
import shlex
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def main():
    combined='--combined-only' in sys.argv
    version='arm-v2' if combined else 'arm-v1'
    out=HERE/('arm-combined-v2' if combined else 'arm-v1');out.mkdir(exist_ok=True)
    assert not list(out.iterdir()), 'refusing to overwrite existing measurements'
    binary=HERE/'builds'/version/'proposal_probe'
    receipt=json.loads((binary.parent/'build.json').read_text())
    assert a.sha(binary)==receipt['binary_sha256']
    assert a.sha(binary.parent/'proposal_probe.c')==receipt['source_sha256']
    manifest=json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())
    old=manifest['remote_directory'];remote='/mnt/glrtbench/lag-discovery-'+str(int(time.time()))
    a.remote('mkdir '+shlex.quote(remote));a.upload(binary,remote+'/proposal_probe')
    assert a.remote('sha256sum '+remote+'/proposal_probe').split()[0]==a.sha(binary)
    expected={}
    for line in (HERE/'ds7-704-v1/rows.jsonl').read_text().splitlines():
        row=json.loads(line);c=row['context'];expected[(c['session_id'],c['visit_index'],row['window'],row['rx'])]=row
    results=[]
    for i,ctx in enumerate(manifest['selected']):
        edge=ctx['target']['edge'];templates=a.template_map()[edge]
        assert a.remote(f'sha256sum {old}/{edge}-exact.c128').split()[0]==templates['exact']['sha256']
        data=np.load(a.INPUTS/ctx['file'],allow_pickle=False)
        import hashlib
        assert a.remote(f'sha256sum {old}/case-{i}.ci16').split()[0]==hashlib.sha256(data.tobytes()).hexdigest()
        for rep in range(3):
            cmd=[remote+'/proposal_probe','2500000',old+'/'+edge+'-exact.c128',old+f'/case-{i}.ci16']
            if combined:cmd.append('--combined-only')
            raw=a.remote(shlex.join(cmd),timeout=60)
            (out/f'case-{i}-r{rep}.jsonl').write_text(raw)
            rows=[json.loads(s) for s in raw.splitlines()];assert len(rows)==22
            assert {(r['probe_index'],r['receiver_id']) for r in rows}=={(w,rx) for w in range(11) for rx in range(2)}
            mismatch=[]
            for r in rows:
                oldrow=expected[(ctx['session_id'],ctx['visit_index'],r['probe_index'],r['receiver_id'])]
                for method,values in r['top4' if combined else 'top32'].items():
                    expected_values=oldrow['ranked_epochs'][method][:4] if combined else oldrow['ranked_epochs'][method]
                    if values!=expected_values:
                        mismatch.append({'window':r['probe_index'],'rx':r['receiver_id'],'method':method,
                            'top4_equal':values[:4]==oldrow['ranked_epochs'][method][:4],
                            'native':values,'python':expected_values})
            total={key:sum(r['timings_ms'][key] for r in rows) for key in rows[0]['timings_ms']}
            results.append({'case':i,'repeat':rep,'context':ctx,'timings_ms':total,'rank_mismatches':mismatch})
            print(i,rep,total,'mismatches',len(mismatch),flush=True)
    summary={'complete':True,'scope':'CPU0 proposal only; no GLRT scoring or capture',
        'binary_sha256':a.sha(binary),'build_receipt_sha256':a.sha(binary.parent/'build.json'),
        'remote_directory':remote,'rows':results,'mean_timings_ms':{
            key:sum(r['timings_ms'][key] for r in results)/len(results) for key in results[0]['timings_ms']},
        'top32_mismatches':sum(len(r['rank_mismatches']) for r in results),
        'top4_mismatches':sum(not m['top4_equal'] for r in results for m in r['rank_mismatches'])}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(summary['mean_timings_ms'],flush=True)

if __name__=='__main__':main()
