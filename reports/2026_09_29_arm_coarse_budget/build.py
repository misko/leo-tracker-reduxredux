#!/usr/bin/env python3
"""Build isolated CI16-normalized coarse-budget artifacts; no device execution."""
from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources/coarse-budget'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
CONFIGS={'fastscale-full':16,'fastscale-frame2':2,'fastscale-frame4':4,'fastscale-frame8':8}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True)
    return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,source,name,frames):
    arm=target=='arm'; sanitizer=target=='sanitizer'
    cmd=[ARM_CC if arm else 'gcc','-DLEO_PRESENCE_FFTW=1','-std=c11','-O1' if sanitizer else '-O3',
         '-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',
         '-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2',
         '-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1',f'-DLEO_PRESENCE_COARSE_FRAMES={frames}']
    if arm: cmd += ['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitizer: cmd += ['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd += ['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd += [ARM_FFTW,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm']
    if sanitizer: cmd.append('-fsanitize=address,undefined')
    return cmd+['-o',str(out/name)]
def build(target):
    out=ROOT/'builds'/target
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SOURCE,out); commands=[]; binaries=[]
    for label,frames in CONFIGS.items():
        cohort=f'cohort_{label}_{target}'
        if target!='sanitizer':
            commands.append(run(command(out,target,'cohort_probe.c',cohort,frames))); binaries.append(out/cohort)
        test=f'test_{label}_{target}'
        commands.append(run(command(out,target,'test_direct_glrt.c',test,frames))); binaries.append(out/test)
        if target!='arm':
            check=subprocess.run([str(out/test)],text=True,capture_output=True,check=True)
            commands.append({'command':[str(out/test)],'stdout':check.stdout,'stderr':check.stderr})
    receipt={'schema':'arm-coarse-budget-build/v1','target':target,
      'configurations':{'ci16_fixed_scale':32768,'coarse_frames':CONFIGS,
        'qualification':'finite integral CI16 samples only; no nonfinite floating-input claim'},
      'semantics':'Fixed scale changes only the coarse FP32 normalization. Final GLRT is unchanged; reduced coarse frames are detector variants.',
      'commands':commands,'binaries':{p.name:sha(p) for p in binaries},
      'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'receipt_sha256':sha(out/'build-receipt.json')}
def main():
    records={target:build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-coarse-budget-matrix/v1','source':str(SOURCE),'builds':records},indent=2)+'\n')
if __name__=='__main__': main()
