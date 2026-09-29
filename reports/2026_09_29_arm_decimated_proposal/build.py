#!/usr/bin/env python3
"""Build factor-1/2/4 proposal-resolution artifacts."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def build(target,factor):
    out=ROOT/'builds'/f'{target}-factor{factor}'
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math',f'-DLEO_PROPOSAL_DECIMATION={factor}']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_LAG_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    commands=[];binaries=[]
    for source,stem in [('proposal_probe.c','proposal_probe'),('test_neon_fold.c','test_neon_fold'),('test_decimation.c','test_decimation')]:
        name=f'{stem}_{target}_factor{factor}';cmd=[cc,*flags,str(out/source)]+(([ARM_FFTW] if arm else ['-lfftw3f']))+['-lm','-o',str(out/name)]
        commands.append(run(cmd));binaries.append(out/name)
    units=[]
    if not arm:
        for stem in ('test_neon_fold','test_decimation'):
            p=subprocess.run([str(out/f'{stem}_{target}_factor{factor}')],text=True,capture_output=True,check=True)
            units.append({'binary':f'{stem}_{target}_factor{factor}','executed':True,'stdout':p.stdout,'stderr':p.stderr})
    receipt={'schema':'arm-decimated-proposal-build/v1','target':target,'factor':factor,
      'semantics':'original-grid lag1/3/5 and power; feature block averages before reduced-grid correlation/ranking; output epoch=factor*bin',
      'commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{p.name:sha(p) for p in sorted(out.glob('*.c'))}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    builds={f'{target}-factor{factor}':build(target,factor) for target in ('host','arm') for factor in (1,2,4)}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-decimated-proposal-matrix/v1','builds':builds},indent=2)+'\n')
if __name__=='__main__':main()
