#!/usr/bin/env python3
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def build(target):
    out=ROOT/'builds'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out)
    cc=ARM_CC if target=='arm' else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math','-fno-math-errno','-fno-trapping-math']
    if target=='arm':flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    binary=out/f'diagnose_decimated_fir_{target}'
    command=[cc,*flags,'-I',str(out),str(out/'decimated_fir.c'),str(out/'diagnose_decimated_fir.c'),'-lm','-o',str(binary)]
    proc=subprocess.run(command,text=True,capture_output=True)
    if proc.returncode:raise RuntimeError(json.dumps({'command':command,'stdout':proc.stdout,'stderr':proc.stderr,'returncode':proc.returncode},indent=2))
    receipt={'schema':'arm-decimated-fine-neon-diagnostic/v1','target':target,
        'purpose':'preserve 3e-6 relative test bound and print first failing pattern/rate/index plus numerical scale',
        'command':command,'stdout':proc.stdout,'stderr':proc.stderr,
        'binary':{'path':binary.name,'sha256':sha(binary)},
        'sources':{p.name:sha(p) for p in out.iterdir() if p.suffix in ('.c','.h')}}
    if target=='host':
        run=subprocess.run([str(binary)],text=True,capture_output=True)
        receipt['unit']={'executed':True,'returncode':run.returncode,'stdout':run.stdout,'stderr':run.stderr}
        if run.returncode:raise RuntimeError(json.dumps(receipt['unit'],indent=2))
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
if __name__=='__main__':
    builds={target:build(target) for target in ('host','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-decimated-fine-neon-diagnostic-matrix/v1','builds':builds},indent=2)+'\n')
