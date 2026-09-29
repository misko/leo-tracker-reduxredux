#!/usr/bin/env python3
"""Build immutable final-GLRT/conditioned reuse artifacts."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,source,name,skip,budget):
    arm=target=='arm';san=target=='sanitizer';cc=ARM_CC if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}',f'-DSKIP_CONDITIONED_RECHECK={skip}','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:flags+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if san:flags+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd=[cc,*flags,'-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
    if san:cmd+=['-fsanitize=address,undefined']
    return cmd+['-o',str(out/name)]
def build(target):
    out=ROOT/'builds'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);commands=[];binaries=[];units=[]
    if target!='sanitizer':
        for skip,label in ((0,'checked'),(1,'rawcondition')):
            name=f'cohort_final_reuse_f2_{label}_{target}';commands.append(run(command(out,target,'cohort_probe.c',name,skip,2)));binaries.append(out/name)
    tests=(('test_final_reuse.c','test_final_reuse'),('test_direct_glrt.c','test_direct_glrt'),('test_fine_precision.c','test_fine_budget'))
    for source,stem in tests:
        name=f'{stem}_{target}';commands.append(run(command(out,target,source,name,0,0)));binaries.append(out/name)
        if target!='arm':
            p=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            units.append({'binary':name,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
    receipt={'schema':'arm-final-reuse-build/v1','target':target,'baseline':'integrated_scorer/builds-fast/host-v3 fine2 checked/rawcondition',
      'cache_scope':'per leo_full_search_run window/RX; exact epoch, binary64 CFO bits, sample count',
      'commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},
      'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-final-reuse-matrix/v1','builds':records},indent=2)+'\n')
if __name__=='__main__':main()
