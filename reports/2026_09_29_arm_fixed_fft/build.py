"""Create immutable Q15/Q7 fixed fine-FFT snapshots from raw-v2."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_fine_precision'/'builds'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1: raise RuntimeError(f'{path}: expected one occurrence, got {text.count(old)}: {old[:50]}')
    path.write_text(text.replace(old,new))

def main():
    arm='--arm' in sys.argv; sanitize='--sanitize' in sys.argv; bits=7 if '--q7' in sys.argv else 15
    if arm and sanitize: raise SystemExit('--sanitize is host-only')
    source_name=('arm' if arm else 'host')+'-raw-v2'
    flavor=('arm' if arm else 'host-asan' if sanitize else 'host')+f'-q{bits}-v7'
    out=HERE/'builds'/flavor
    if out.exists(): raise SystemExit(f'refusing to overwrite {out}')
    shutil.copytree(BASE/source_name,out)
    shutil.copy2(HERE/'implementation'/'fixed_fft.h',out/'fixed_fft.h')
    shutil.copy2(HERE/'implementation'/'fine_fixed.h',out/'fine_fixed.h')
    shutil.copy2(HERE/'tests'/'test_fixed_fft.c',out/'test_fixed_fft.c')
    src=out/'full_search.c'
    once(src,'#include "fine_precision.h"','#include "fine_fixed.h"')
    src.write_text(src.read_text().replace('leo_fine_precision_cache','leo_fine_fixed_cache')
        .replace('leo_fine_precision_init','leo_fine_fixed_init')
        .replace('leo_fine_precision_scores','leo_fine_fixed_scores')
        .replace('leo_fine_precision_free','leo_fine_fixed_free'))
    old='''    out.fine_precision_calls=fine_cache.calls;
    out.fine_precision_guard_checks=fine_cache.guard_checks;
    out.fine_precision_fallbacks=fine_cache.fallbacks;
    out.fine_precision_nonfinite_fallbacks=fine_cache.nonfinite_fallbacks;
    out.fine_precision_near_tie_fallbacks=fine_cache.near_tie_fallbacks;
    out.fine_precision_interpolation_fallbacks=fine_cache.interpolation_fallbacks;'''
    new='''    out.fine_precision_calls=fine_cache.calls;
    out.fine_precision_guard_checks=0;
    out.fine_precision_fallbacks=0;
    out.fine_precision_nonfinite_fallbacks=0;
    out.fine_precision_near_tie_fallbacks=0;
    out.fine_precision_interpolation_fallbacks=0;
    out.fine_fixed_fraction_bits=fine_cache.fft.fraction_bits;
    out.fine_fixed_stages=fine_cache.fft.stages;
    out.fine_fixed_block_scale=(int32_t)fine_cache.fft.block_scale;
    out.fine_fixed_clips=(int32_t)fine_cache.fft.clips;'''
    once(src,old,new)
    hdr=out/'full_search.h'
    once(hdr,'    int32_t fine_precision_near_tie_fallbacks, fine_precision_interpolation_fallbacks;',
         '    int32_t fine_precision_near_tie_fallbacks, fine_precision_interpolation_fallbacks;\n'
         '    int32_t fine_fixed_fraction_bits, fine_fixed_stages;\n'
         '    int32_t fine_fixed_block_scale, fine_fixed_clips;')
    runner=out/'cohort_probe.c'
    once(runner,'\\"fine_precision_interpolation_fallbacks\\":%d,\\"timings_ms\\"',
        '\\"fine_precision_interpolation_fallbacks\\":%d,\\"fine_fixed_fraction_bits\\":%d,\\"fine_fixed_stages\\":%d,\\"fine_fixed_block_scale\\":%d,\\"fine_fixed_clips\\":%d,\\"timings_ms\\"')
    once(runner,'r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,r->total_cpu_ms',
        'r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,r->fine_fixed_fraction_bits,r->fine_fixed_stages,r->fine_fixed_block_scale,r->fine_fixed_clips,r->total_cpu_ms')
    test=out/'test_fine_precision.c'
    text=test.read_text().replace('leo_fine_precision_cache','leo_fine_fixed_cache')
    text=text.replace('leo_fine_precision_init','leo_fine_fixed_init').replace('leo_fine_precision_scores','leo_fine_fixed_scores').replace('leo_fine_precision_free','leo_fine_fixed_free')
    text=text.replace('test_guard_classifier();','').replace('fine precision passed: FP32 spectra, guard classifier, cache, partial frames, all rates','fine fixed passed: integer spectra, cache, partial frames, all rates')
    text=text.replace('assert(fabs(candidate[k]-fp64[k])<=2e-5*fmax(1.0,fabs(fp64[k])));','assert(fabs(candidate[k]-fp64[k])<=0.004*fmax(1.0,fabs(fp64[k])));')
    # The now-unused guard test references symbols absent from the fixed header.
    begin=text.index('static void test_guard_classifier(void)'); end=text.index('static void run_rate',begin)
    test.write_text(text[:begin]+text[end:])
    receipt=json.loads((out/'fine-precision-build.json').read_text()); commands=[]
    for record in receipt['commands']:
        cmd=[arg.replace(str(BASE/source_name),str(out)) for arg in record['command']]
        cmd.insert(1,f'-DLEO_FIXED_FFT_BITS={bits}')
        if sanitize:
            cmd=['-O1' if x=='-O3' else x for x in cmd]
            cmd[1:1]=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
            cmd.insert(-2,'-fsanitize=address,undefined')
        run=subprocess.run(cmd,capture_output=True,text=True,check=True); commands.append({'command':cmd,'compiler_stdout':run.stdout,'compiler_stderr':run.stderr})
    cc=commands[0]['command'][0] if arm else 'gcc'
    unit_cmd=[cc,f'-DLEO_FIXED_FFT_BITS={bits}','-std=c11','-O2','-Wall','-Wextra','-I',str(out),str(out/'test_fixed_fft.c'),'-lm','-o',str(out/'test_fixed_fft')]
    if sanitize: unit_cmd[1:1]=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined'];unit_cmd.insert(-2,'-fsanitize=address,undefined')
    run=subprocess.run(unit_cmd,capture_output=True,text=True,check=True); commands.append({'command':unit_cmd,'compiler_stdout':run.stdout,'compiler_stderr':run.stderr})
    unit_stdout='cross-build only; ARM execution belongs to root\n'
    if not arm:
        runs=[]
        for binary in (out/'test_fixed_fft',out/'test_fine_precision'):
            r=subprocess.run([str(binary)],capture_output=True,text=True,check=True); runs.append(r.stdout)
        unit_stdout=''.join(runs)
    binaries=[out/'cohort_fine_precision',out/'test_fine_precision',out/'test_fixed_fft']
    result={'schema':'arm-fixed-fine-fft-build/v1','algorithm':'integer-mixed-radix-2/3/5','fraction_bits':bits,'arm':arm,'sanitize':sanitize,
      'source_baseline':str(BASE/source_name),'source_baseline_receipt_sha256':sha(BASE/source_name/'fine-precision-build.json'),
      'invariants':{'lengths':[5000,10000,15000,20000],'block_scale':'N','frequency_grid':'unchanged','scorer':'FP64','fallback':'none'},
      'commands':commands,'unit_stdout':unit_stdout,'binaries':{p.name:sha(p) for p in binaries},
      'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'fixed-fft-build.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'fine-precision-build.json').unlink()

if __name__=='__main__': main()
