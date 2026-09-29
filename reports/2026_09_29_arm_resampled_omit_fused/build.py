#!/usr/bin/env python3
"""Build the power-of-two-resampled, omit-power fused proposal prototype."""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def flags(target,sanitize=False,budget=2):
    arm=target=='arm';f=['-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-DLEO_PROPOSAL_OMIT_POWER=1','-DLEO_NEON_CONDITIONED_MOMENTS=1','-std=c11','-O1' if sanitize else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:f+=['-Werror','-Wno-error=lto-type-mismatch','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    if sanitize:f+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    return f
def link_command(out,target,sources,name,sanitize=False,budget=2):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    c=[cc,*flags(target,sanitize,budget),'-I',str(out/'src/native_presence'),'-I',str(out),*[str(out/s) for s in sources],str(out/'conditioned_czt.c'),str(out/'fft_full.c')]
    c+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
    if sanitize:c+=['-fsanitize=address,undefined']
    return c+['-o',str(out/name)]
def proposal_test_command(out,target,source,name,sanitize=False):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    c=[cc,*flags(target,sanitize,0),'-I',str(out),str(out/source)]
    c+=([ARM_FFTW] if arm else ['-lfftw3f'])+['-lm']
    if sanitize:c+=['-fsanitize=address,undefined']
    return c+['-o',str(out/name)]
def build(target):
    out=ROOT/'builds'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);san=target=='sanitizer';commands=[];binaries=[];units=[]
    name=f'fused_resampled_omit_power_neon_moments_{target}'
    link=link_command(out,target,['fused_probe.c','proposal_core.c'],name,san)
    core=str(out/'proposal_core.c');obj=str(out/'proposal_core.o');prefix=link[:link.index('-I')]
    commands.append(run([*prefix,'-fno-lto','-c',core,'-o',obj]));link[link.index(core)]=obj
    commands.append(run(link));binaries.append(out/name)
    for source,stem in [('test_resampling.c','test_resampling'),('test_resampled_omit_core.c','test_omit_component'),('test_final_reuse.c','test_final_reuse'),('test_fine_precision.c','test_fine_budget'),('test_moment_accuracy.c','test_moment_accuracy')]:
        unit=f'{stem}_{target}';cmd=proposal_test_command(out,target,source,unit,san) if source.startswith('test_resam') else link_command(out,target,[source],unit,san,0)
        commands.append(run(cmd));binaries.append(out/unit)
        if target!='arm':
            p=subprocess.run([str(out/unit)],text=True,capture_output=True,check=True);units.append({'binary':unit,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
    receipt={'schema':'arm-resampled-omit-fused-build/v1','target':target,'proposal_feature_mask':['lag1','lag3','lag5'],'proposal_transform':'periodic linear interpolation from native proposal bins to the next power of two; rank and top-four centres map back to native bins','search_feature':'frozen fused V4 with NEON conditioned moments v2 and FP64 final GLRT','scope':'research-only fused runner; no ARM execution performed by this build; input/template reads, workspace setup and JSON printing excluded from outer timer','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
def main():
    records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-resampled-omit-fused-matrix/v1','builds':records},indent=2)+'\n')
if __name__=='__main__':main()
