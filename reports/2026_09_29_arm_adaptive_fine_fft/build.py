#!/usr/bin/env python3
"""Build threshold variants of the lazy second-endpoint fine FFT."""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent; SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command):
    done=subprocess.run(command,text=True,capture_output=True,check=True)
    return {'command':command,'stdout':done.stdout,'stderr':done.stderr}
def command(out,target,source,name,skip=1,budget=2,ratio='1.5'):
    arm=target=='arm'; san=target=='sanitizer'; cc=ARM_CC if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-DLEO_NEON_CONDITIONED_MOMENTS=1',f'-DLEO_FINE_ADAPTIVE_RATIO={ratio}','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}',f'-DSKIP_CONDITIONED_RECHECK={skip}','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm: flags += ['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if san: flags += ['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd=[cc,*flags,'-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd += ([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
    if san: cmd += ['-fsanitize=address,undefined']
    return cmd+['-o',str(out/name)]
def build(target):
    out=ROOT/'builds'/target
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SOURCE,out); commands=[]; binaries=[]; units=[]
    if target!='sanitizer':
        for ratio in ('1.25','1.5','2.0'):
            name=f'cohort_adaptive_{ratio.replace(".","_")}_{target}'
            commands.append(run(command(out,target,'cohort_probe.c',name,1,2,ratio))); binaries.append(out/name)
    for source,stem in (('test_final_reuse.c','test_final_reuse'),('test_moment_accuracy.c','test_moment_accuracy'),('test_adaptive_fine.c','test_adaptive_fine')):
        name=f'{stem}_{target}'; commands.append(run(command(out,target,source,name,0,2,'1.5'))); binaries.append(out/name)
        if target!='arm':
            done=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            units.append({'binary':name,'executed':True,'stdout':done.stdout,'stderr':done.stderr})
    receipt={'schema':'arm-adaptive-fine-fft-build/v1','target':target,
      'feature':'lazy second endpoint FFT after first-endpoint peak dominance test; ratios 1.25, 1.5 and 2.0; 500 Hz grid/interpolation and final GLRT unchanged',
      'commands':commands,'units':units,'binaries':{path.name:sha(path) for path in binaries},
      'sources':{str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file() and path.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    records={target:build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-adaptive-fine-fft-matrix/v1','builds':records},indent=2)+'\n')
if __name__=='__main__': main()
