#!/usr/bin/env python3
"""Build exact linear-top-four proposal with pre-map score rejection."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
 p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,sources,name,san=False,budget=2):
 arm=target=='arm';cc=ARM_CC if arm else 'gcc';f=['-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-DLEO_PROPOSAL_OMIT_POWER=1','-DLEO_NEON_CONDITIONED_MOMENTS=1','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
 if arm:f+=['-Werror','-Wno-error=lto-type-mismatch','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
 if san:f+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
 c=[cc,*f,'-I',str(out/'src/native_presence'),'-I',str(out),*[str(out/s) for s in sources],str(out/'conditioned_czt.c'),str(out/'fft_full.c')]
 c+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
 if san:c+=['-fsanitize=address,undefined']
 return c+['-o',str(out/name)]
def build(target):
 out=ROOT/'builds'/target
 if out.exists():shutil.rmtree(out)
 shutil.copytree(SOURCE,out);san=target=='sanitizer';commands=[];binaries=[];units=[];name=f'fused_proposal_rank_fast_{target}'
 link=command(out,target,['fused_probe.c','proposal_core.c'],name,san);core=str(out/'proposal_core.c');obj=str(out/'proposal_core.o');prefix=link[:link.index('-I')]
 commands.append(run([*prefix,'-fno-lto','-c',core,'-o',obj]));link[link.index(core)]=obj;commands.append(run(link));binaries.append(out/name)
 for source,stem in [('test_rank_fast.c','test_rank_fast'),('test_final_reuse.c','test_final_reuse'),('test_fine_precision.c','test_fine_budget'),('test_moment_accuracy.c','test_moment_accuracy')]:
  unit=f'{stem}_{target}';commands.append(run(command(out,target,[source],unit,san,0)));binaries.append(out/unit)
  if target!='arm':
   p=subprocess.run([str(out/unit)],text=True,capture_output=True,check=True);units.append({'binary':unit,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
 receipt={'schema':'arm-proposal-rank-fast-v2-build/v1','target':target,'proposal_feature_mask':['lag1','lag3','lag5'],'rank_additions':'exact float rank/(z-1) values precomputed at workspace setup','top4':'four linear local-maximum passes; candidates unable to beat the ascending-index best skip index mapping and exclusion checks','scope':'all proposal features, 22 windows, four centres, radius-two regions and search work retained','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
if __name__=='__main__':
 records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
