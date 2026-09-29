"""Build the bounded direct-CI16/limited-complex integration."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_compile_pack'/'sources'/'limited-complex-v2'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_FFTWF='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise RuntimeError(f'{path}: count={text.count(old)} for {old[:60]!r}')
    path.write_text(text.replace(old,new))

def prepare(out):
    shutil.copytree(BASE,out)
    fs=out/'full_search.c'
    once(fs,'#include "presence.c"','''/* Active only during the synchronous CI16 entry point. */
static const int16_t *leo_full_ci16_samples;
static size_t leo_full_ci16_stride;
#include "presence.c"''')
    presence=out/'src/native_presence/presence.c'
    once(presence,'if (integer) received = w->samples[start+k+integer_offset];','''if (integer && final_scoring && leo_full_ci16_samples) {
                    size_t at=(size_t)(start+k+integer_offset)*leo_full_ci16_stride;
                    __real__ received=(double)leo_full_ci16_samples[at];
                    __imag__ received=(double)leo_full_ci16_samples[at+1];
                } else if (integer) received = w->samples[start+k+integer_offset];''')
    old='''                correlations[0][symbol-first_symbol] += received*w->glrt_exact_rotated[k];
                correlations[1][symbol-first_symbol] += received*w->glrt_control_rotated[k];'''
    new='''                double xr=creal(received),xi=cimag(received);
                double er=creal(w->glrt_exact_rotated[k]),ei=cimag(w->glrt_exact_rotated[k]);
                double cr=creal(w->glrt_control_rotated[k]),ci=cimag(w->glrt_control_rotated[k]);
                int local_symbol=symbol-first_symbol;
                __real__ correlations[0][local_symbol] += xr*er-xi*ei;
                __imag__ correlations[0][local_symbol] += xr*ei+xi*er;
                __real__ correlations[1][local_symbol] += xr*cr-xi*ci;
                __imag__ correlations[1][local_symbol] += xr*ci+xi*cr;'''
    once(presence,old,new)
    old='''int leo_full_search_run(leo_presence_workspace *w,
    const leo_presence_complex *samples, size_t count, leo_full_search_result *result)
{
    if (!result) return -1;
    leo_full_search_result out={0};
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    if (ingest(w,samples,count)) return -1;'''
    new='''static int leo_full_search_run_ingested(leo_presence_workspace *w,size_t count,
    leo_full_search_result *result,double cpu,double wall,double conversion_ms)
{
    if (!result) return -1;
    leo_full_search_result out={0};
    out.conversion_cpu_ms=conversion_ms;'''
    once(fs,old,new)
    once(fs,'    out.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;\n    double started=',
         '    double started=')
    marker='''    *result=out;
    return 0;
}
'''
    wrappers='''    *result=out;
    return 0;
}

int leo_full_search_run(leo_presence_workspace *w,const leo_presence_complex *samples,
    size_t count,leo_full_search_result *result)
{
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);
    if(ingest(w,samples,count))return -1;
    return leo_full_search_run_ingested(w,count,result,cpu,wall,
        clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu);
}

int leo_full_search_run_ci16(leo_presence_workspace *w,const int16_t *samples,
    size_t scalar_stride,size_t count,leo_full_search_result *result)
{
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);
    if(!w||!samples||scalar_stride<2||fegetround()!=FE_TONEAREST||
       count<(size_t)ceil(w->rate/375.0)||count>w->max_samples)return -1;
    for(size_t k=0;k<count;++k)
        w->samples[k]=(double)samples[k*scalar_stride]+I*(double)samples[k*scalar_stride+1];
    leo_full_ci16_samples=samples;leo_full_ci16_stride=scalar_stride;
    int status=leo_full_search_run_ingested(w,count,result,cpu,wall,
        clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu);
    leo_full_ci16_samples=NULL;leo_full_ci16_stride=0;
    return status;
}
'''
    # Replace the final occurrence, not earlier helper returns.
    pos=fs.read_text().rfind(marker)
    if pos<0:raise RuntimeError('final function marker absent')
    text=fs.read_text();fs.write_text(text[:pos]+wrappers+text[pos+len(marker):])
    hdr=out/'full_search.h'
    once(hdr,'''int leo_full_search_run(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    leo_full_search_result *result);''','''int leo_full_search_run(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    leo_full_search_result *result);
int leo_full_search_run_ci16(leo_presence_workspace *workspace,
    const int16_t *samples, size_t scalar_stride, size_t count,
    leo_full_search_result *result);''')
    cohort=out/'cohort_probe.c'
    once(cohort,'leo_presence_workspace *w=leo_presence_create(rate,exact,control,frame); leo_presence_complex *samples=calloc(probe,sizeof(*samples)); if(!w||!samples)return 3;',
         'leo_presence_workspace *w=leo_presence_create(rate,exact,control,frame); if(!w)return 3;')
    old='''        } for(size_t i=0;i<probe;i++){size_t at=((size_t)window*stride+i)*4+rx*2;samples[i]=(leo_presence_complex){ci16[at],ci16[at+1]};} leo_full_search_result r; if(leo_full_search_run(w,samples,probe,&r)) return 4; emit(rx,window,&r); fflush(stdout); }'''
    new='''        } const int16_t *view=ci16+4*(size_t)window*stride+2*rx;
        leo_full_search_result r; if(leo_full_search_run_ci16(w,view,4,probe,&r)) return 4;
        emit(rx,window,&r); fflush(stdout); }'''
    once(cohort,old,new)
    once(cohort,'fclose(regions);leo_presence_destroy(w);free(samples);free(ci16);free(control);free(exact);return 0;',
         'fclose(regions);leo_presence_destroy(w);free(ci16);free(control);free(exact);return 0;')
    direct=out/'test_direct_glrt.c'
    if not direct.read_text().startswith('static int regional_count;'):
        direct.write_text('static int regional_count;\nstatic int regional_epochs[13334];\n'+direct.read_text())
    shutil.copy2(HERE/'tests'/'test_ci16_integration.c',out/'test_ci16_integration.c')

def command(out,target,source,name,sanitize=False):
    arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    cmd=[cc,'-DLEO_PRESENCE_FFTW=1','-std=c11','-O1' if sanitize else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:cmd+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:cmd+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    cmd+=['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
    cmd+=([ARM_FFTWF,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm'])
    if sanitize:cmd+=['-fsanitize=address,undefined']
    return cmd+['-o',str(out/name)]

def build(target):
    out=HERE/'builds'/f'{target}-v3'
    if out.exists():raise SystemExit(f'refusing overwrite {out}')
    prepare(out);records=[];binaries=[]
    jobs=[('cohort_probe.c','cohort_integrated'),('test_fine_precision.c','test_fine_precision'),('test_direct_glrt.c','test_direct_glrt'),('test_ci16_integration.c','test_ci16_integration')]
    for source,name in jobs:
        cmd=command(out,target,source,name)
        run=subprocess.run(cmd,text=True,capture_output=True,check=True)
        records.append({'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
    tests=[]
    if target=='host':
        for name in ('test_fine_precision','test_direct_glrt','test_ci16_integration'):
            run=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            tests.append({'binary':name,'stdout':run.stdout,'stderr':run.stderr})
    receipt={'schema':'arm-integrated-scorer-build/v1','target':target,'baseline':str(BASE),'baseline_sha256':sha(HERE.parent/'2026_09_29_arm_compile_pack'/'builds'/'limited-complex-v2'/('arm' if target=='arm' else 'host')/'build-receipt.json'),'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    targets=['arm'] if '--arm-only' in sys.argv else ['host','arm']
    for target in targets:build(target)
