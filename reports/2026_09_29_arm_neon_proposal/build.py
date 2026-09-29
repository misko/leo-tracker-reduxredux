#!/usr/bin/env python3
"""Build scalar-host and NEON-ARM proposal-fold artifacts."""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent; SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True)
    return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def build(target):
    out=ROOT/'builds'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out)
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_LAG_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    commands=[];binaries=[]
    for source,name in [('proposal_probe.c',f'proposal_probe_{target}'),('test_neon_fold.c',f'test_neon_fold_{target}')]:
        cmd=[cc,*flags,str(out/source)]
        cmd+=([ARM_FFTW] if arm else ['-lfftw3f'])+['-lm','-o',str(out/name)]
        commands.append(run(cmd));binaries.append(out/name)
    unit={'executed':False,'stdout':'','stderr':''}
    if not arm:
        p=subprocess.run([str(out/'test_neon_fold_host')],text=True,capture_output=True,check=True)
        unit={'executed':True,'stdout':p.stdout,'stderr':p.stderr}
    receipt={'schema':'arm-neon-proposal-build/v1','target':target,
      'implementation':'scalar' if not arm else 'NEON vld4 CI16 deinterleave with exact per-frame accumulation order',
      'commands':commands,'unit':unit,'binaries':{p.name:sha(p) for p in binaries},
      'sources':{p.name:sha(p) for p in sorted(out.glob('*.c'))}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    records={t:build(t) for t in ('host','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-neon-proposal-matrix/v1','builds':records},indent=2)+'\n')
if __name__=='__main__':main()
