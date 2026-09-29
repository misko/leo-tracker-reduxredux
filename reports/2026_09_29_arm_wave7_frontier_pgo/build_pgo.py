#!/usr/bin/env python3
"""Build/freeze Cortex-A9 PGO generate or use artifacts at stable paths."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources'; WORK=ROOT/'work'/'arm'
PROFILE_DIR=Path('/var/tmp/leo-wave7-frontier-radius1-pgo-profile')
CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
INC='/var/tmp/leo-fftw-float-20260912/install/include'
FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
COMMON=['-DCONDITIONED_MOMENT_BLOCK=64','-DLEO_PRESENCE_FFTW=1','-DLEO_PROPOSAL_LIBRARY','-DLEO_PROPOSAL_OMIT_POWER=1','-DLEO_NEON_CONDITIONED_MOMENTS=1','-DLEO_TRACK_MIN_MATCHES=1','-DLEO_PROPOSAL_FRAME_BUDGET=8','-DLEO_PROPOSAL_FFT_DIVISOR=2','-std=c11','-O3','-Wall','-Wextra','-Werror','-Wno-error=lto-type-mismatch','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range','-DLEO_FINE_FRAME_BUDGET_DEFAULT=2','-DSKIP_CONDITIONED_RECHECK=1','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{INC}']

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def invoke(command,cwd=None):
    p=subprocess.run(command,text=True,capture_output=True,check=True,cwd=cwd)
    return {'command':command,'stdout':p.stdout,'stderr':p.stderr}
def prepare(reset):
    if reset and WORK.exists(): shutil.rmtree(WORK)
    if not WORK.exists(): shutil.copytree(SOURCE,WORK)
    expected={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    actual={str(p.relative_to(WORK)):sha(p) for p in WORK.rglob('*') if p.is_file() and p.suffix in ('.c','.h')}
    if actual!=expected: raise SystemExit('stable work source differs from frozen source')
def flags(mode):
    option=f'-fprofile-{mode}={PROFILE_DIR}'
    result=[*COMMON,option]
    if mode=='use': result+=['-fprofile-correction','-Werror=coverage-mismatch']
    return result
def command(srcs,name,mode,budget=2):
    f=[x if not x.startswith('-DLEO_FINE_FRAME_BUDGET_DEFAULT=') else f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={budget}' for x in flags(mode)]
    return [CC,*f,'-I',str(WORK/'src/native_presence'),'-I',str(WORK),*[str(WORK/s) for s in srcs],str(WORK/'conditioned_czt.c'),str(WORK/'fft_full.c'),FFTW,'-lfftw3','-lm','-o',str(WORK/name)]
def unit_command(source,name,mode):
    extra=['proposal_tracking.c'] if source=='test_proposal_tracking.c' else []
    c=command([source,*extra],name,mode,0)
    if mode=='use':
        c=[x for x in c if not (x.startswith('-fprofile-use=') or x in ('-fprofile-correction','-Werror=coverage-mismatch','-Werror=missing-profile'))]
    return c
def build(mode):
    prepare(mode=='generate')
    expected_profiles=('proposal_core.gcda','proposal_tracking.gcda','conditioned_czt.gcda','fft_full.gcda','fused_probe.gcda')
    if mode=='use':
        missing=[name for name in expected_profiles if not (PROFILE_DIR/name).is_file() or not (PROFILE_DIR/name).stat().st_size]
        if missing: raise SystemExit('missing/nonempty ARM profiles: '+', '.join(missing))
    commands=[]; binary='fused_wave7_frontier_radius1_pgo_arm'
    link=command(['fused_probe.c','proposal_core.c','proposal_tracking.c'],binary,mode)
    core=str(WORK/'proposal_core.c'); obj=str(WORK/'proposal_core.o'); prefix=link[:link.index('-I')]
    commands.append(invoke([*prefix,'-fno-lto','-c','proposal_core.c','-o','proposal_core.o'],WORK))
    link[link.index(core)]=obj;commands.append(invoke(link))
    units=[]
    for source,stem in [('test_proposal_budget.c','test_proposal_budget'),('test_proposal_tracking.c','test_proposal_tracking'),('test_dwell_input.c','test_dwell_input'),('test_fused_fold.c','test_fused_fold'),('test_rank_radix11.c','test_rank_radix11'),('test_direct_ci16_ingest.c','test_direct_ci16_ingest'),('test_sparse_peak_scan.c','test_sparse_peak_scan'),('test_rate_coarse_gate.c','test_rate_coarse_gate'),('test_final_reuse.c','test_final_reuse'),('test_fine_precision.c','test_fine_budget'),('test_moment_accuracy.c','test_moment_accuracy')]:
        name=f'{stem}_arm';commands.append(invoke(unit_command(source,name,mode)));units.append(name)
    frozen=ROOT/'builds'/mode
    if frozen.exists(): raise SystemExit(f'{frozen} already exists; artifacts are immutable')
    frozen.mkdir(parents=True)
    for name in [binary,*units]: shutil.copy2(WORK/name,frozen/name)
    profile_names=[]
    p=subprocess.run(['strings',str(WORK/binary)],text=True,capture_output=True,check=True)
    profile_names=sorted({line for line in p.stdout.splitlines() if line.endswith('.gcda')})
    for p in WORK.rglob('*'):
        if p.is_file() and p.suffix in ('.c','.h'):
            destination=frozen/p.relative_to(WORK);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
    receipt={'schema':'arm-wave7-frontier-radius1-pgo-build/v1','mode':mode,'profile_dir':str(PROFILE_DIR),'stable_work':str(WORK),'coarse_score_thresholds':{'2500000':.312,'5000000':.150,'7500000':.175,'10000000':.152},'selection':'Wave7 full-coarse proposal8 half-grid tracking-min1 radius1 plus Cortex-A9 PGO; approximate proposal geometry','sources':{str(p.relative_to(WORK)):sha(p) for p in sorted(WORK.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')},'commands':commands,'expected_profiles':list(expected_profiles),'expected_gcda_strings':profile_names,'training_policy':'same four arm4-v2 metadata contexts; held-out32 timing and parity excludes them','binaries':{p.name:sha(p) for p in frozen.iterdir() if p.is_file() and p.suffix not in ('.c','.h')}}
    (frozen/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    manifest={'mode':mode,'receipt_sha256':sha(frozen/'build-receipt.json'),'binary_sha256':sha(frozen/binary),'expected_gcda_strings':profile_names}
    (ROOT/f'{mode}-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('generate','use'));args=ap.parse_args();build(args.mode)
if __name__=='__main__':main()
