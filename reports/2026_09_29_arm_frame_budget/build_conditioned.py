#!/usr/bin/env python3
"""Build self-contained host, sanitizer and ARM frame-budget artifacts."""
from __future__ import annotations
import hashlib, json, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources/conditioned-frame-budget'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
BUDGETS=(0,1,2,4,8)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def execute(command):
    result=subprocess.run(command,text=True,capture_output=True,check=True)
    return {'command':command,'stdout':result.stdout,'stderr':result.stderr}

def command(out,target,source,name,budget=None):
    arm=target=='arm'; sanitize=target=='sanitizer'
    cmd=[ARM_CC if arm else 'gcc','-DLEO_PRESENCE_FFTW=1','-std=c11',
         '-O1' if sanitize else '-O3','-Wall','-Wextra','-fno-fast-math',
         '-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',
         '-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN',
         '-DLEO_FULL_REFINEMENT_MODE=2']
    if budget is not None: cmd.append(f'-DLEO_CONDITIONED_FRAME_BUDGET_DEFAULT={budget}')
    if arm: cmd += ['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize: cmd += ['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd += ['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),
            str(out/source),str(out/'fft_full.c')]
    cmd += [ARM_FFTW,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm']
    if sanitize: cmd.append('-fsanitize=address,undefined')
    return cmd+['-o',str(out/name)]

def build(target):
    out=ROOT/'builds-conditioned'/target
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SOURCE,out)
    commands=[]; binaries=[]
    if target!='sanitizer':
        for budget in BUDGETS:
            label='full' if budget==0 else str(budget)
            name=f'cohort_frame_{label}_{target}'
            commands.append(execute(command(out,target,'cohort_probe.c',name,budget)))
            binaries.append(out/name)
    test_name=f'test_conditioned_frame_budget_{target}'
    commands.append(execute(command(out,target,'test_direct_glrt.c',test_name)))
    binaries.append(out/test_name)
    unit={'executed':False,'stdout':'','stderr':''}
    if target!='arm':
        result=subprocess.run([str(out/test_name)],text=True,capture_output=True,check=True)
        unit={'executed':True,'stdout':result.stdout,'stderr':result.stderr}
    sources={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*'))
             if p.is_file() and p.suffix in ('.c','.h')}
    receipt={'schema':'arm-conditioned-frame-budget-build/v1','variant':'conditioned-frame-budget','target':target,
      'runtime_configuration':{'environment':'LEO_CONDITIONED_FRAME_BUDGET','allowed':[1,2,4,8],
        'unset':'all available frames','compiled_binaries':{'full':0,'1':1,'2':2,'4':4,'8':8}},
      'scientific_semantics':('Limited-complex-v2 finite-input semantics. Frame cap applies only to '
        'conditioned frequency scoring, including FP64 rechecks; candidates/windows and final FP64 GLRT remain unchanged.'),
      'commands':commands,'unit':unit,'binaries':{p.name:sha(p) for p in binaries},'sources':sources}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),
            'receipt_sha256':sha(out/'build-receipt.json')}

def main():
    records={target:build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'conditioned-build-manifest.json').write_text(json.dumps({'schema':'arm-conditioned-frame-budget-matrix/v1',
      'source':str(SOURCE),'builds':records},indent=2)+'\n')

if __name__=='__main__': main()
