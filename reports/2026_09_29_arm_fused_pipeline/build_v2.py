#!/usr/bin/env python3
"""Build the fused proposal/search research prototype."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources-v2'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,sources,name,sanitize=False,budget=2):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-std=c11','-O1' if sanitize else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:flags+=['-Werror','-Wno-error=lto-type-mismatch','-fno-strict-aliasing','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    if sanitize:flags+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd=[cc,*flags,'-I',str(out/'src/native_presence'),'-I',str(out),*[str(out/s) for s in sources],str(out/'conditioned_czt.c'),str(out/'fft_full.c')]
    cmd+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
    if sanitize:cmd+=['-fsanitize=address,undefined']
    return cmd+['-o',str(out/name)]
def build(target):
    out=ROOT/'builds-v2'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);san=target=='sanitizer';commands=[];binaries=[];units=[]
    name=f'fused_pipeline_v2_{target}';commands.append(run(command(out,target,['fused_probe.c','proposal_core.c'],name,san)));binaries.append(out/name)
    for source,stem in [('test_final_reuse.c','test_final_reuse'),('test_fine_precision.c','test_fine_budget')]:
        unit=f'{stem}_{target}';commands.append(run(command(out,target,[source],unit,san,0)));binaries.append(out/unit)
        if target!='arm':
            p=subprocess.run([str(out/unit)],text=True,capture_output=True,check=True);units.append({'binary':unit,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
    receipt={'schema':'arm-fused-pipeline-build/v2','target':target,'scope':'single outer per-window process CPU timer includes proposal, region construction, CI16 conversion and search; input/template reads, workspace setup and JSON printing excluded','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest-v2.json').write_text(json.dumps({'schema':'arm-fused-pipeline-matrix/v2','builds':records},indent=2)+'\n')
if __name__=='__main__':main()
