#!/usr/bin/env python3
"""Build Wave6 dwell-input, fused-fold, and exact radix-rank combination."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;VARIANTS={'313':.313,'3135':.3135,'314':.314,'320':.320,'325':.325,'330':.330}
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
THRESHOLDS={'2500000':.312,'5000000':.150,'7500000':.175,'10000000':.152}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
 p=subprocess.run(cmd,text=True,capture_output=True,check=True);return {'command':cmd,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,sources,name,minimum,san=False,budget=2):
 arm=target=='arm';cc=ARM_CC if arm else 'gcc';f=['-DCONDITIONED_MOMENT_BLOCK=64','-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-DLEO_PROPOSAL_OMIT_POWER=1','-DLEO_NEON_CONDITIONED_MOMENTS=1','-DLEO_PROPOSAL_FRAME_BUDGET=8','-DLEO_PROPOSAL_FFT_DIVISOR=2','-DLEO_PRESENCE_COARSE_FRAMES=16','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
 f.insert(0,f'-DLEO_TRACK_MIN_MATCHES={minimum}')
 if arm:f+=['-Werror','-Wno-error=lto-type-mismatch','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
 if san:f+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
 c=[cc,*f,'-I',str(out/'src/native_presence'),'-I',str(out),*[str(out/s) for s in sources],str(out/'conditioned_czt.c'),str(out/'fft_full.c')]
 c+=([ARM_FFTW,'-lfftw3'] if arm else ['-lfftw3f','-lfftw3'])+['-lm']
 if san:c+=['-fsanitize=address,undefined']
 return c+['-o',str(out/name)]
def build(variant,target):
 minimum=1;threshold=VARIANTS[variant];source=ROOT/f'sources-{variant}';out=ROOT/f'builds-{variant}'/target
 if out.exists():shutil.rmtree(out)
 shutil.copytree(source,out);san=target=='sanitizer';commands=[];binaries=[];units=[];name=f'fused_wave8_gate_{variant}_{target}'
 link=command(out,target,['fused_probe.c','proposal_core.c','proposal_tracking.c'],name,minimum,san);core=str(out/'proposal_core.c');obj=str(out/'proposal_core.o');prefix=link[:link.index('-I')]
 commands.append(run([*prefix,'-fno-lto','-c',core,'-o',obj]));link[link.index(core)]=obj;commands.append(run(link));binaries.append(out/name)
 for source,stem,extra in [('test_rank_histograms.c','test_rank_histograms',[]),('test_proposal_budget.c','test_proposal_budget',[]),('test_proposal_tracking.c','test_proposal_tracking',['proposal_tracking.c']),('test_dwell_input.c','test_dwell_input',[]),('test_fused_fold.c','test_fused_fold',[]),('test_rank_radix11.c','test_rank_radix11',[]),('test_direct_ci16_ingest.c','test_direct_ci16_ingest',[]),('test_sparse_peak_scan.c','test_sparse_peak_scan',[]),('test_rate_coarse_gate.c','test_rate_coarse_gate',[]),('test_final_reuse.c','test_final_reuse',[]),('test_fine_precision.c','test_fine_budget',[]),('test_moment_accuracy.c','test_moment_accuracy',[])]:
  unit=f'{stem}_{target}';commands.append(run(command(out,target,[source,*extra],unit,minimum,san,0)));binaries.append(out/unit)
  if target!='arm':
   p=subprocess.run([str(out/unit)],text=True,capture_output=True,check=True);units.append({'binary':unit,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
 thresholds={**THRESHOLDS,'2500000':threshold}
 receipt={'schema':'arm-wave8-gate-frontier-build/v1','target':target,'variant':variant,'coarse_score_thresholds':thresholds,'conditioned_degree':2,'conditioned_block':64,'selection':'Wave8 exact-rank frontier with raised 2.5 MS/s coarse gate','proposal_feature_mask':['lag1','lag3','lag5'],'scope':'all 22 windows retained; only 2.5 MS/s coarse threshold changes; proposal geometry remains approximate; final GLRT FP64 unchanged','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('variants',nargs='+',choices=VARIANTS);ap.add_argument('--target',choices=('host','sanitizer','arm'),default='host');args=ap.parse_args()
 records={f'{v}/{args.target}':build(v,args.target) for v in args.variants};path=ROOT/f'build-manifest-{args.target}.json';prior=json.loads(path.read_text()) if path.exists() else {};prior.update(records);path.write_text(json.dumps(prior,indent=2)+'\n')
