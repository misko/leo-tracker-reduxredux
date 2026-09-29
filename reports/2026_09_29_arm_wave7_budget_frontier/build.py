#!/usr/bin/env python3
"""Build explicit approximate 8- and 4-frame proposal-budget variants."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
THRESHOLDS={'2500000':.312,'5000000':.150,'7500000':.175,'10000000':.152}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
 p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,sources,name,san=False,budget=2,proposal_frames=16,fft_divisor=1,coarse_frames=16):
 arm=target=='arm';cc=ARM_CC if arm else 'gcc';f=['-DCONDITIONED_MOMENT_BLOCK=64','-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-DLEO_PROPOSAL_OMIT_POWER=1','-DLEO_NEON_CONDITIONED_MOMENTS=1',f'-DLEO_PROPOSAL_FRAME_BUDGET={proposal_frames}',f'-DLEO_PROPOSAL_FFT_DIVISOR={fft_divisor}',f'-DLEO_PRESENCE_COARSE_FRAMES={coarse_frames}','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
 if arm:f+=['-Werror','-Wno-error=lto-type-mismatch','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
 if san:f+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
 c=[cc,*f,'-I',str(out/'src/native_presence'),'-I',str(out),*[str(out/s) for s in sources],str(out/'conditioned_czt.c'),str(out/'fft_full.c')]
 c+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
 if san:c+=['-fsanitize=address,undefined']
 return c+['-o',str(out/name)]
def build(target,label,proposal_frames,fft_divisor,coarse_frames):
 out=ROOT/f'builds-{label}'/target
 if out.exists():shutil.rmtree(out)
 shutil.copytree(SOURCE,out);san=target=='sanitizer';commands=[];binaries=[];units=[];name=f'fused_budget_frontier_{label}_{target}'
 link=command(out,target,['fused_probe.c','proposal_core.c'],name,san,2,proposal_frames,fft_divisor,coarse_frames);core=str(out/'proposal_core.c');obj=str(out/'proposal_core.o');prefix=link[:link.index('-I')]
 commands.append(run([*prefix,'-fno-lto','-c',core,'-o',obj]));link[link.index(core)]=obj;commands.append(run(link));binaries.append(out/name)
 for source,stem in [('test_proposal_budget.c','test_proposal_budget'),('test_dwell_input.c','test_dwell_input'),('test_fused_fold.c','test_fused_fold'),('test_rank_radix11.c','test_rank_radix11'),('test_direct_ci16_ingest.c','test_direct_ci16_ingest'),('test_sparse_peak_scan.c','test_sparse_peak_scan'),('test_rate_coarse_gate.c','test_rate_coarse_gate'),('test_final_reuse.c','test_final_reuse'),('test_fine_precision.c','test_fine_budget'),('test_moment_accuracy.c','test_moment_accuracy')]:
  unit=f'{stem}_{target}';commands.append(run(command(out,target,[source],unit,san,0,proposal_frames,fft_divisor,coarse_frames)));binaries.append(out/unit)
  if target!='arm':
   p=subprocess.run([str(out/unit)],text=True,capture_output=True,check=True);units.append({'binary':unit,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
 receipt={'schema':'arm-wave7-proposal-budget-build/v1','target':target,'coarse_score_thresholds':THRESHOLDS,'conditioned_degree':2,'conditioned_block':64,'selection':'sealed Wave6 combined with approximate evenly-spaced proposal-frame budget only','proposal_frame_budget':proposal_frames,'proposal_fft_divisor':fft_divisor,'coarse_frame_budget':coarse_frames,'proposal_frame_indices':[round(q*15/(proposal_frames-1)) for q in range(proposal_frames)] if proposal_frames>1 else [0],'proposal_feature_mask':['lag1','lag3','lag5'],'proposal_fold_scratch_bytes':{'per_complex_buffer':8,'buffers_total':'3*n*8','incremental_over_one_buffer':'2*n*8'},'scope':'approximate proposal selection only; support recomputed from selected original frames; full downstream coarse, conditioned, and FP64 final GLRT retain their original frame configuration','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
if __name__=='__main__':
 variants={'coarse8':(16,1,8),'proposal8_halfgrid':(8,2,16),'triple':(8,2,8)};records={label:{t:build(t,label,*config) for t in ('host','sanitizer','arm')} for label,config in variants.items()};(ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
