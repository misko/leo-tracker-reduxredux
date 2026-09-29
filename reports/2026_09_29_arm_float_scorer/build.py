"""Build an FP32 final matched-filter candidate from integrated scorer v3."""
import hashlib,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_integrated_scorer'/'builds'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_FFTWF='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise RuntimeError(f'{path}: count {text.count(old)} for {old[:60]!r}')
    path.write_text(text.replace(old,new))

HELPER=r'''
static void glrt_float_symbol_dot(const double complex *samples,int sample_start,
    int begin,int end,const float *exact,const float *control,
    double complex *exact_sum,double complex *control_sum)
{
    float er[4]={0},ei[4]={0},cr[4]={0},ci[4]={0}; int k=begin;
#if defined(__ARM_NEON)
    float32x4_t ver=vdupq_n_f32(0),vei=ver,vcr=ver,vci=ver;
    for(;k+3<end;k+=4) {
        float xr[4],xi[4];
        if(leo_full_ci16_samples && leo_full_ci16_stride==4) {
            const int16_t *p=leo_full_ci16_samples+4*(size_t)(sample_start+k);
            int16x4x4_t q=vld4_s16(p);
            vst1q_f32(xr,vcvtq_f32_s32(vmovl_s16(q.val[0])));
            vst1q_f32(xi,vcvtq_f32_s32(vmovl_s16(q.val[1])));
        } else for(int j=0;j<4;++j) {
            xr[j]=(float)creal(samples[sample_start+k+j]);
            xi[j]=(float)cimag(samples[sample_start+k+j]);
        }
        float32x4_t xrv=vld1q_f32(xr),xiv=vld1q_f32(xi);
        float32x4x2_t e=vld2q_f32(exact+2*k),c=vld2q_f32(control+2*k);
        ver=vaddq_f32(ver,vsubq_f32(vmulq_f32(xrv,e.val[0]),vmulq_f32(xiv,e.val[1])));
        vei=vaddq_f32(vei,vaddq_f32(vmulq_f32(xrv,e.val[1]),vmulq_f32(xiv,e.val[0])));
        vcr=vaddq_f32(vcr,vsubq_f32(vmulq_f32(xrv,c.val[0]),vmulq_f32(xiv,c.val[1])));
        vci=vaddq_f32(vci,vaddq_f32(vmulq_f32(xrv,c.val[1]),vmulq_f32(xiv,c.val[0])));
    }
    vst1q_f32(er,ver);vst1q_f32(ei,vei);vst1q_f32(cr,vcr);vst1q_f32(ci,vci);
#else
    for(;k+3<end;k+=4)for(int j=0;j<4;++j) {
        float xr=(float)creal(samples[sample_start+k+j]),xi=(float)cimag(samples[sample_start+k+j]);
        er[j]+=xr*exact[2*(k+j)]-xi*exact[2*(k+j)+1];
        ei[j]+=xr*exact[2*(k+j)+1]+xi*exact[2*(k+j)];
        cr[j]+=xr*control[2*(k+j)]-xi*control[2*(k+j)+1];
        ci[j]+=xr*control[2*(k+j)+1]+xi*control[2*(k+j)];
    }
#endif
    double a=0,b=0,c=0,d=0;for(int j=0;j<4;++j){a+=er[j];b+=ei[j];c+=cr[j];d+=ci[j];}
    for(;k<end;++k) {
        float xr=(float)creal(samples[sample_start+k]),xi=(float)cimag(samples[sample_start+k]);
        a+=(float)(xr*exact[2*k]-xi*exact[2*k+1]);b+=(float)(xr*exact[2*k+1]+xi*exact[2*k]);
        c+=(float)(xr*control[2*k]-xi*control[2*k+1]);d+=(float)(xr*control[2*k+1]+xi*control[2*k]);
    }
    *exact_sum=a+I*b;*control_sum=c+I*d;
}
'''

def prepare(out):
    presence=out/'src/native_presence/presence.c'
    once(presence,'#include <time.h>','#include <time.h>\n#if defined(__ARM_NEON)\n#include <arm_neon.h>\n#endif')
    once(presence,'static int glrt(leo_presence_workspace *w, size_t count, int epoch,',HELPER+'\nstatic int glrt(leo_presence_workspace *w, size_t count, int epoch,')
    anchor='''    double previous_fraction = NAN, weights[16], normalizer = 0;
    for (int frame = 0; frame < frame_limit; ++frame) {'''
    replacement='''    float *float_exact=NULL,*float_control=NULL;
    if(final_scoring && integer) {
        float_exact=malloc(2*w->n*sizeof(*float_exact));float_control=malloc(2*w->n*sizeof(*float_control));
        if(!float_exact||!float_control){free(float_exact);free(float_control);return -1;}
        for(size_t k=0;k<w->n;++k) {
            float_exact[2*k]=(float)creal(w->glrt_exact_rotated[k]);float_exact[2*k+1]=(float)cimag(w->glrt_exact_rotated[k]);
            float_control[2*k]=(float)creal(w->glrt_control_rotated[k]);float_control[2*k+1]=(float)cimag(w->glrt_control_rotated[k]);
        }
    }
    double previous_fraction = NAN, weights[16], normalizer = 0;
    for (int frame = 0; frame < frame_limit; ++frame) {'''
    once(presence,anchor,replacement)
    anchor='''        for (int symbol = first_symbol; symbol < first_symbol+64; ++symbol) {
            int begin = symbol_start(w,symbol);
            int end = symbol_start(w,symbol+1);
            for (int k = begin; k < end; ++k) {'''
    replacement='''        for (int symbol = first_symbol; symbol < first_symbol+64; ++symbol) {
            int begin = symbol_start(w,symbol);
            int end = symbol_start(w,symbol+1);
            if(final_scoring && integer) {
                glrt_float_symbol_dot(w->samples,start+integer_offset,begin,end,float_exact,float_control,
                    &correlations[0][symbol-first_symbol],&correlations[1][symbol-first_symbol]);
                continue;
            }
            for (int k = begin; k < end; ++k) {'''
    once(presence,anchor,replacement)
    once(presence,'    result[2] = 0;','    free(float_exact);free(float_control);\n    result[2] = 0;')
    shutil.copy2(HERE/'tests'/'test_float_dot.c',out/'test_float_dot.c')

def command(out,target,source,name):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    cmd=[cc,'-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:cmd+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    cmd+=['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd+=([ARM_FFTWF,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm'])
    return cmd+['-o',str(out/name)]

def build(target):
    out=HERE/'builds'/f'{target}-v2';source=BASE/f'{target}-v3'
    if out.exists():raise SystemExit(f'refusing overwrite {out}')
    shutil.copytree(source,out);prepare(out);records=[];binaries=[]
    for src,name in [('cohort_probe.c','cohort_float_scorer'),('test_fine_precision.c','test_fine_precision'),('test_direct_glrt.c','test_direct_glrt'),('test_ci16_integration.c','test_float_integration'),('test_float_dot.c','test_float_dot')]:
        cmd=command(out,target,src,name);run=subprocess.run(cmd,text=True,capture_output=True,check=True)
        records.append({'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
    tests=[]
    if target=='host':
        for name in ('test_fine_precision','test_direct_glrt','test_float_integration','test_float_dot'):
            run=subprocess.run([str(out/name)],text=True,capture_output=True)
            tests.append({'binary':name,'returncode':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
    receipt={'schema':'arm-float-final-scorer-build/v1','target':target,'baseline_receipt_sha256':sha(source/'build-receipt.json'),'precision':{'matched_filter_products':'FP32','partial_sums':'four stable FP32 lanes','template_preparation':'local FP32, timed','frames':16,'symbols':64,'energy_normalization':'FP64','residual_fft_selection':'FP64','fallback':'none'},'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    for target in ('host','arm'):build(target)
