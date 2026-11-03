"""Serial RAM-based ARM GLRT plus separately timed native PSD proposals."""
import argparse
import json
import re
import shlex
import sys
from pathlib import Path

from features import HERE, sha
from run_native import mask_for

sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort

UPLOAD=arm_cohort.upload
REMOTE=arm_cohort.remote


def run(inputs,baseline,build,output,method):
    selected=json.loads((inputs/'inputs.json').read_text())['rows'];assert len(selected)==4
    threshold=json.loads((HERE/'method-selection.json').read_text())['threshold']
    receipt=json.loads((build/'build.json').read_text())
    for name in ('cohort_mask','test_mask'):
        assert sha(build/name)==receipt['binary_sha256'][name]
    psd_receipt=json.loads((HERE/'psd-builds.json').read_text())['arm']
    assert sha(build/'psd_probe')==psd_receipt['binary_sha256']
    psd_rows=[]

    def upload(source,destination):
        UPLOAD(source,destination)
        match=re.search(r'/case-(\d+)\.ci16$',destination)
        if not match:return
        i=int(match[1]);ctx=selected[i];remote_dir=destination.rsplit('/',1)[0]
        bank=inputs/f"{ctx['target']['edge']}.bank"
        if i==0:UPLOAD(build/'psd_probe',remote_dir+'/psd_probe')
        UPLOAD(bank,remote_dir+'/psd.bank')
        hashes=REMOTE(f'cd {shlex.quote(remote_dir)} && sha256sum psd_probe psd.bank case-{i}.ci16')
        actual_hashes={line.split()[1]:line.split()[0] for line in hashes.splitlines()}
        assert actual_hashes=={'psd_probe':sha(build/'psd_probe'),'psd.bank':sha(bank),f'case-{i}.ci16':sha(source)}
        command=f'cd {shlex.quote(remote_dir)} && chmod 755 psd_probe && ./psd_probe 2500000 psd.bank case-{i}.ci16'
        stdout=REMOTE(command,timeout=120)
        rows=[json.loads(x) for x in stdout.splitlines()];assert len(rows)==22
        expected=ctx['psd_windows']
        for actual,wanted in zip(rows,expected,strict=True):
            assert (actual['receiver_id'],actual['probe_index'])==(wanted['receiver_id'],wanted['probe_index'])
            assert actual['ranking']==wanted['proposal']['ranking']
            assert actual['sqrt_ranking']==wanted['proposal']['sqrt_ranking']
            assert mask_for(actual,method,threshold)==mask_for(wanted['proposal'],method,threshold)
            psd_rows.append(dict(context={k:v for k,v in ctx.items() if k!='psd_windows'},native=actual))
        path=output/f'psd-case-{i}.jsonl';path.write_text(stdout)
        maskpath=output/f'masks-{i}.txt';maskpath.write_text('\n'.join(str(mask_for(w,method,threshold)) for w in rows)+'\n')
        UPLOAD(maskpath,remote_dir+f'/masks-{i}.txt')

    def remote(command,timeout=15):
        if './test_screen' in command:
            command=command.replace('./test_screen','./test_screen --smoke2p5');timeout=max(timeout,180)
        if './cohort 2500000' in command:
            command=re.sub(r'(case-(\d+)\.ci16) >',r'\1 masks-\2.txt >',command)
        return REMOTE(command,timeout)

    arm_cohort.INPUTS=inputs;arm_cohort.BASELINE=baseline
    arm_cohort.select_four=lambda rows:selected
    arm_cohort.upload=upload;arm_cohort.remote=remote
    arm_cohort.run(build/'cohort_mask',build/'test_mask',output)
    (output/'psd-rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in psd_rows))
    total_psd=sum(r['native']['cpu_ms'] for r in psd_rows)/1000
    summary=json.loads((output/'summary.json').read_text())
    glrt=summary['timing_ms_per_dwell']['total_cpu']/1000
    result=dict(method=method,dwells=4,glrt_cpu_seconds_per_dwell=glrt,
        psd_cpu_seconds_per_dwell=total_psd/4,
        combined_cpu_seconds_per_dwell=glrt+(0 if method=='full' else total_psd/4),
        scope='Sum of separately timed PSD and GLRT stages; planning/transfer excluded; full control has no PSD cost',
        psd_mask_parity=True,psd_bank_sha256={e:sha(inputs/f'{e}.bank') for e in ('lower','upper')},
        psd_binary_sha256=sha(build/'psd_probe'),wrapper_sha256=sha(Path(__file__)))
    (output/'stage-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--method',required=True)
    a=p.parse_args();run(a.inputs.resolve(),a.baseline.resolve(),a.build.resolve(),a.output,a.method)
