#!/usr/bin/env python3
"""Build immutable factor-4 cached-reciprocal normalization artifacts."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources/factor4-reciprocal'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def build(target):
    out=ROOT/'builds'/f'{target}-factor4-reciprocal'
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math','-DLEO_PROPOSAL_DECIMATION=4']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_LAG_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    commands=[];binaries=[]
    cases=[('proposal_probe.c','proposal_probe'),('test_neon_fold.c','test_neon_fold'),('test_decimation.c','test_decimation'),('test_reciprocal.c','test_reciprocal')]
    for source,stem in cases:
        name=f'{stem}_{target}_factor4_reciprocal';cmd=[cc,*flags,str(out/source)]+([ARM_FFTW] if arm else ['-lfftw3f'])+['-lm','-o',str(out/name)]
        commands.append(run(cmd));binaries.append(out/name)
    units=[]
    if not arm:
        for _,stem in cases[1:]:
            p=subprocess.run([str(out/f'{stem}_{target}_factor4_reciprocal')],text=True,capture_output=True,check=True)
            units.append({'binary':f'{stem}_{target}_factor4_reciprocal','executed':True,'stdout':p.stdout,'stderr':p.stderr})
    receipt={'schema':'arm-decimated-proposal-reciprocal-build/v1','target':target,'factor':4,
      'rounding_semantics':'cached FP32 reciprocal multiply replaces per-cell division; support zero maps to exact zero; no fast-math',
      'commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.glob('*.c'))}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    builds={target:build(target) for target in ('host','arm')}
    (ROOT/'reciprocal-build-manifest.json').write_text(json.dumps({'schema':'arm-decimated-proposal-reciprocal-matrix/v1','builds':builds},indent=2)+'\n')
if __name__=='__main__':main()
