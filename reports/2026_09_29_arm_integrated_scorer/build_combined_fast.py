"""Build the preferred FP64-final fine/coarse/moments combination."""
import hashlib,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
MOMENTS=ROOT/'2026_09_29_arm_conditioned_moments'
BASE=MOMENTS/'sources'/'conditioned-moments-v3'
FINE=ROOT/'2026_09_29_arm_frame_budget'/'sources'/'frame-budget'
COARSE=ROOT/'2026_09_29_arm_coarse_budget'/'sources'/'coarse-budget'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_FFTWF='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise RuntimeError(f'{path}: count={text.count(old)} {old[:50]!r}')
    path.write_text(text.replace(old,new))

def prepare(out):
    shutil.copytree(BASE,out)
    shutil.copy2(FINE/'fine_precision.h',out/'fine_precision.h')
    shutil.copy2(FINE/'test_fine_precision.c',out/'test_fine_precision.c')
    shutil.copy2(COARSE/'src/native_presence/coarse_fp32.h',out/'src/native_presence/coarse_fp32.h')
    shutil.copy2(COARSE/'test_direct_glrt.c',out/'test_coarse_fast.c')
    fs=out/'full_search.c'
    once(fs,'static double conditioned_screen_guard(void)','static __attribute__((unused)) double conditioned_screen_guard(void)')
    once(fs,'#ifndef LEO_FULL_DIRECT_GLRT','''#ifndef SKIP_CONDITIONED_RECHECK
#define SKIP_CONDITIONED_RECHECK 0
#endif
#if SKIP_CONDITIONED_RECHECK != 0 && SKIP_CONDITIONED_RECHECK != 1
#error "SKIP_CONDITIONED_RECHECK must be 0 or 1"
#endif
#ifndef LEO_FULL_DIRECT_GLRT''')
    old='''    const double guard=conditioned_screen_guard();
    out->conditioned_bins_screened+=nf;
    for(int q=0;q<nf;++q) {
        if(!isfinite(scores[q])||scores[q]>=maximum-2*guard) {
            full_conditioned_scores(w,count,epoch,frequencies+q,1,scores+q,0);
            ++out->conditioned_bins_rechecked;
        } else scores[q]=-INFINITY;
    }'''
    new='''    out->conditioned_bins_screened+=nf;
#if !SKIP_CONDITIONED_RECHECK
    const double guard=conditioned_screen_guard();
    for(int q=0;q<nf;++q) {
        if(!isfinite(scores[q])||scores[q]>=maximum-2*guard) {
            full_conditioned_scores(w,count,epoch,frequencies+q,1,scores+q,0);
            ++out->conditioned_bins_rechecked;
        } else scores[q]=-INFINITY;
    }
#else
    (void)maximum;
#endif'''
    once(fs,old,new)
    old='''        const double guard=conditioned_screen_guard();
        out.conditioned_bins_screened+=nf;
        for (int q=0;q<nf;++q) {
            if (!isfinite(scores[q]) || scores[q]>=maximum-2*guard) {
                full_conditioned_scores(w,count,refined,frequencies+q,1,scores+q,0);
                ++out.conditioned_bins_rechecked;
            } else scores[q]=-INFINITY;
        }'''
    new='''        out.conditioned_bins_screened+=nf;
#if !SKIP_CONDITIONED_RECHECK
        const double guard=conditioned_screen_guard();
        for (int q=0;q<nf;++q) {
            if (!isfinite(scores[q]) || scores[q]>=maximum-2*guard) {
                full_conditioned_scores(w,count,refined,frequencies+q,1,scores+q,0);
                ++out.conditioned_bins_rechecked;
            } else scores[q]=-INFINITY;
        }
#else
        (void)maximum;
#endif'''
    once(fs,old,new)
    cohort=out/'cohort_probe.c'
    once(cohort,'\\"fine_precision_mode\\":\\"raw\\",\\"fine_precision_calls\\":%d',
      '\\"fine_precision_mode\\":\\"raw\\",\\"fine_frame_budget\\":%d,\\"coarse_frames\\":16,\\"coarse_fixed_scale\\":32768,\\"conditioned_moments\\":\\"v3\\",\\"conditioned_frames\\":16,\\"skip_conditioned_recheck\\":%d,\\"final_scorer\\":\\"fp64\\",\\"fine_precision_calls\\":%d')
    once(cohort,'r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->fine_precision_calls',
      'r->fine_fft_cache_entries,r->fine_fft_cache_hits,leo_fine_precision_frame_budget,SKIP_CONDITIONED_RECHECK,r->fine_precision_calls')
    once(cohort,'    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);','''    const char *budget_text=getenv("LEO_FINE_FRAME_BUDGET");
    if(budget_text) {char *budget_end;errno=0;long budget=strtol(budget_text,&budget_end,10);
        if(errno||*budget_end||leo_fine_precision_set_frame_budget((int)budget))return 2;}
    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);''')

def command(out,target,source,name,fine,skip):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    cmd=[cc,'-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range',f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={fine}',f'-DSKIP_CONDITIONED_RECHECK={skip}','-DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1','-DLEO_PRESENCE_COARSE_FRAMES=16','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:cmd+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    cmd+=['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd+=([ARM_FFTWF,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm'])
    return cmd+['-o',str(out/name)]

def build(target):
    out=HERE/'builds-fast'/f'{target}-v3'
    if out.exists():raise SystemExit(f'refusing overwrite {out}')
    prepare(out);records=[];binaries=[]
    for fine in (2,4):
      for skip,label in ((0,'checked'),(1,'rawcondition')):
        name=f'cohort_fast_f{fine}_{label}';cmd=command(out,target,'cohort_probe.c',name,fine,skip)
        run=subprocess.run(cmd,text=True,capture_output=True,check=True);records.append({'fine_budget':fine,'skip_conditioned_recheck':skip,'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
    tests=[]
    for source,name in [('test_fine_precision.c','test_fine_budget'),('test_direct_glrt.c','test_direct_glrt'),('test_moments.c','test_moments'),('test_coarse_fast.c','test_coarse_fast')]:
        cmd=command(out,target,source,name,0,0);run=subprocess.run(cmd,text=True,capture_output=True,check=True);records.append({'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
        if target=='host':
            t=subprocess.run([str(out/name)],text=True,capture_output=True,check=True);tests.append({'binary':name,'stdout':t.stdout,'stderr':t.stderr})
    receipt={'schema':'arm-integrated-fast-build/v1','target':target,'preferred':{'fine_budget':2,'skip_conditioned_recheck':0,'coarse_frames':16,'coarse_scale':32768,'conditioned_frames':16,'conditioned_moments':'v3','final_scorer':'FP64'},'experimental_raw_condition':{'macro':'SKIP_CONDITIONED_RECHECK','value':1,'meaning':'select approximate conditioned screen scores directly; no FP64 near-max rechecks'},'baselines':{'moments_v3_receipt_sha256':sha(MOMENTS/'builds-v3'/target/'build-receipt.json'),'fine_budget_receipt_sha256':sha(ROOT/'2026_09_29_arm_frame_budget'/'builds'/target/'build-receipt.json'),'coarse_budget_receipt_sha256':sha(ROOT/'2026_09_29_arm_coarse_budget'/'builds'/target/'build-receipt.json')},'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    for target in ('host','arm'):build(target)
