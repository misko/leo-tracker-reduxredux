"""Build short-only and both FP32 GLRT FFT variants."""
import hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parent/'2026_09_29_arm_compile_pack'/'sources'/'limited-complex-v2'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_FFTWF='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(path,old,new):
 text=path.read_text()
 if text.count(old)!=1:raise RuntimeError(f'{path}: {text.count(old)} {old[:50]!r}')
 path.write_text(text.replace(old,new))

def prepare(out):
 shutil.copytree(BASE,out);p=out/'src/native_presence/presence.c'
 once(p,'#include <time.h>','#include <time.h>\n#include <fftw3.h>')
 once(p,'    leo_fft fine_fft, short_fft, glrt_fft;','''    leo_fft fine_fft, short_fft, glrt_fft;
    fftwf_complex *glrt_f32_input[2],*glrt_f32_output[2];
    fftwf_plan glrt_f32_plan[2];''')
 once(p,'    leo_fft_free(&w->fine_fft); leo_fft_free(&w->short_fft); leo_fft_free(&w->glrt_fft);','''    leo_fft_free(&w->fine_fft); leo_fft_free(&w->short_fft); leo_fft_free(&w->glrt_fft);
    for(int q=0;q<2;++q){if(w->glrt_f32_plan[q])fftwf_destroy_plan(w->glrt_f32_plan[q]);fftwf_free(w->glrt_f32_input[q]);fftwf_free(w->glrt_f32_output[q]);}''')
 helper='''
static int glrt_float_fft_forward(leo_presence_workspace *w,leo_fft *fft,
    const double complex *input,size_t n,int final)
{
    int slot=final?1:0;
    if(!w->glrt_f32_plan[slot]) {
        w->glrt_f32_input[slot]=fftwf_alloc_complex(n);w->glrt_f32_output[slot]=fftwf_alloc_complex(n);
        if(w->glrt_f32_input[slot]&&w->glrt_f32_output[slot])w->glrt_f32_plan[slot]=fftwf_plan_dft_1d((int)n,w->glrt_f32_input[slot],w->glrt_f32_output[slot],FFTW_FORWARD,FFTW_ESTIMATE);
        if(!w->glrt_f32_plan[slot])return -1;
    }
    for(size_t k=0;k<n;++k)w->glrt_f32_input[slot][k]=(float)creal(input[k])+I*(float)cimag(input[k]);
    fftwf_execute(w->glrt_f32_plan[slot]);
    for(size_t k=0;k<n;++k)fft->output[k]=(double)crealf(w->glrt_f32_output[slot][k])+I*(double)cimagf(w->glrt_f32_output[slot][k]);
    return 0;
}
'''
 once(p,'static int glrt(leo_presence_workspace *w, size_t count, int epoch,',helper+'\nstatic int glrt(leo_presence_workspace *w, size_t count, int epoch,')
 # Exactly two short sites and one final site occur in GLRT.
 text=p.read_text();old='leo_fft_forward(&w->short_fft, w->input);';assert text.count(old)==2
 text=text.replace(old,'#if LEO_GLRT_FLOAT_SHORT\n            if(glrt_float_fft_forward(w,&w->short_fft,w->input,128,0))return -1;\n#else\n            leo_fft_forward(&w->short_fft,w->input);\n#endif',1)
 text=text.replace(old,'#if LEO_GLRT_FLOAT_SHORT\n        if(glrt_float_fft_forward(w,&w->short_fft,w->input,128,0))return -1;\n#else\n        leo_fft_forward(&w->short_fft,w->input);\n#endif',1)
 old='leo_fft_forward(&w->glrt_fft, w->input);';assert text.count(old)==1
 text=text.replace(old,'#if LEO_GLRT_FLOAT_FINAL\n        if(glrt_float_fft_forward(w,&w->glrt_fft,w->input,512,1))return -1;\n#else\n        leo_fft_forward(&w->glrt_fft,w->input);\n#endif')
 p.write_text(text)
 c=out/'cohort_probe.c';once(c,'\\"fine_precision_mode\\":\\"raw\\",\\"fine_precision_calls\\":%d','\\"fine_precision_mode\\":\\"raw\\",\\"glrt_fft_precision\\":\\"%s\\",\\"fine_precision_calls\\":%d');once(c,'r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->fine_precision_calls','r->fine_fft_cache_entries,r->fine_fft_cache_hits,LEO_GLRT_FLOAT_FINAL?"fp32-128-512":"fp32-128",r->fine_precision_calls')
 d=out/'test_direct_glrt.c';d.write_text('static int regional_count;\nstatic int regional_epochs[13334];\n'+d.read_text())
 shutil.copy2(HERE/'tests'/'test_float_glrt_fft.c',out/'test_float_glrt_fft.c')

def command(out,target,source,name,final):
 arm=target=='arm';cc=ARM_CC if arm else 'gcc';cmd=[cc,'-DLEO_GLRT_FLOAT_SHORT=1',f'-DLEO_GLRT_FLOAT_FINAL={final}','-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
 if arm:cmd+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
 cmd+=['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')];cmd+=([ARM_FFTWF,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm']);return cmd+['-o',str(out/name)]

def build(target):
 out=HERE/'builds'/f'{target}-v2'
 if out.exists():raise SystemExit(f'refusing overwrite {out}')
 prepare(out);records=[];binaries=[]
 for final,label in ((0,'short128'),(1,'both128_512')):
  for source,name in [('cohort_probe.c',f'cohort_{label}'),('test_direct_glrt.c',f'test_direct_{label}'),('test_float_glrt_fft.c',f'test_fft_{label}')]:
   cmd=command(out,target,source,name,final);run=subprocess.run(cmd,text=True,capture_output=True,check=True);records.append({'variant':label,'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
 tests=[]
 if target=='host':
  for p in binaries:
   if p.name.startswith('test_'):
    run=subprocess.run([str(p)],text=True,capture_output=True,check=True);tests.append({'binary':p.name,'stdout':run.stdout,'stderr':run.stderr})
 receipt={'schema':'arm-float-glrt-fft-build/v1','target':target,'variants':{'short128':{'short_fft':'FP32','final_fft':'FP64'},'both128_512':{'short_fft':'FP32','final_fft':'FP32'}},'invariants':{'matched_filter':'FP64','energy':'FP64','spectra_accumulation':'FP64','ceilings':'FP64','frames':16,'symbols':64,'fallback':'none','plan_setup':'lazy and timed'},'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}};(out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
 for target in ('host','arm'):build(target)
