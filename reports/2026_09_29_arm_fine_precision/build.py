"""Build immutable raw/guarded FP32 fine-FFT research snapshots."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_fine_reuse'/'builds'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1: raise RuntimeError(f'{path}: replacement count {text.count(old)}')
    path.write_text(text.replace(old,new))

def main():
    arm='--arm' in sys.argv; sanitize='--sanitize' in sys.argv
    mode='guarded' if '--guarded' in sys.argv else 'raw'
    if arm and sanitize: raise SystemExit('--sanitize is host-only')
    baseline='arm-v3' if arm else 'host-v4'
    flavor=('arm-' if arm else 'host-asan-' if sanitize else 'host-')+mode+'-v3'
    out=HERE/'builds'/flavor
    if out.exists(): raise SystemExit(f'refusing to overwrite {out}')
    shutil.copytree(BASE/baseline,out)
    shutil.copy2(HERE/'fine_precision.h',out/'fine_precision.h')
    shutil.copy2(HERE/'test_fine_precision.c',out/'test_fine_precision.c')
    source=out/'full_search.c'
    replace_once(source,'#include "fine_reuse.h"','#include "fine_precision.h"')
    replace_once(source,'leo_fine_reuse_cache fine_cache;\n    leo_fine_reuse_init(&fine_cache,w->fine_fft.size);',
        'leo_fine_precision_cache fine_cache;\n'
        '    if (leo_fine_precision_init(&fine_cache,w->fine_fft.size)) return -1;')
    replace_once(source,'leo_fine_reuse_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)',
        'leo_fine_precision_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)')
    source.write_text(source.read_text().replace('leo_fine_reuse_free(&fine_cache)','leo_fine_precision_free(&fine_cache)'))
    replace_once(source,'out.fine_fft_cache_entries=fine_cache.count;\n    out.fine_fft_cache_hits=fine_cache.hits;',
        'out.fine_fft_cache_entries=fine_cache.count;\n'
        '    out.fine_fft_cache_hits=fine_cache.hits;\n'
        '    out.fine_precision_calls=fine_cache.calls;\n'
        '    out.fine_precision_guard_checks=fine_cache.guard_checks;\n'
        '    out.fine_precision_fallbacks=fine_cache.fallbacks;\n'
        '    out.fine_precision_nonfinite_fallbacks=fine_cache.nonfinite_fallbacks;\n'
        '    out.fine_precision_near_tie_fallbacks=fine_cache.near_tie_fallbacks;\n'
        '    out.fine_precision_interpolation_fallbacks=fine_cache.interpolation_fallbacks;')
    replace_once(source,'    leo_fine_precision_free(&fine_cache);\n    out.acquisition_cpu_ms=',
        '    out.fine_precision_plan_ms=fine_cache.plan_ms;\n'
        '    out.fine_precision_preparation_ms=fine_cache.preparation_ms;\n'
        '    out.fine_precision_execute_ms=fine_cache.execute_ms;\n'
        '    out.fine_precision_storage_ms=fine_cache.storage_ms;\n'
        '    out.fine_precision_score_ms=fine_cache.score_ms;\n'
        '    out.fine_precision_guard_ms=fine_cache.guard_ms;\n'
        '    out.fine_precision_recompute_ms=fine_cache.recompute_ms;\n'
        '    double fine_precision_free_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);\n'
        '    leo_fine_precision_free(&fine_cache);\n'
        '    out.fine_precision_free_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-fine_precision_free_started;\n'
        '    out.acquisition_cpu_ms=')
    header=out/'full_search.h'
    replace_once(header,'    int32_t fine_fft_cache_hits;',
        '    int32_t fine_fft_cache_hits;\n'
        '    int32_t fine_precision_calls, fine_precision_guard_checks;\n'
        '    int32_t fine_precision_fallbacks, fine_precision_nonfinite_fallbacks;\n'
        '    int32_t fine_precision_near_tie_fallbacks, fine_precision_interpolation_fallbacks;\n'
        '    double fine_precision_plan_ms, fine_precision_preparation_ms;\n'
        '    double fine_precision_execute_ms, fine_precision_storage_ms;\n'
        '    double fine_precision_score_ms, fine_precision_guard_ms;\n'
        '    double fine_precision_recompute_ms, fine_precision_free_ms;')
    runner=out/'cohort_probe.c'
    old='\\"fine_fft_cache_hits\\":%d,\\"timings_ms\\"'
    new='\\"fine_fft_cache_hits\\":%d,\\"fine_precision_mode\\":\\"'+mode+'\\",\\"fine_precision_calls\\":%d,\\"fine_precision_guard_checks\\":%d,\\"fine_precision_fallbacks\\":%d,\\"fine_precision_nonfinite_fallbacks\\":%d,\\"fine_precision_near_tie_fallbacks\\":%d,\\"fine_precision_interpolation_fallbacks\\":%d,\\"fine_precision_plan_ms\\":%.17g,\\"fine_precision_preparation_ms\\":%.17g,\\"fine_precision_execute_ms\\":%.17g,\\"fine_precision_storage_ms\\":%.17g,\\"fine_precision_score_ms\\":%.17g,\\"fine_precision_guard_ms\\":%.17g,\\"fine_precision_recompute_ms\\":%.17g,\\"fine_precision_free_ms\\":%.17g,\\"timings_ms\\"'
    replace_once(runner,old,new)
    replace_once(runner,'r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->total_cpu_ms',
        'r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->fine_precision_calls,'
        'r->fine_precision_guard_checks,r->fine_precision_fallbacks,'
        'r->fine_precision_nonfinite_fallbacks,r->fine_precision_near_tie_fallbacks,'
        'r->fine_precision_interpolation_fallbacks,r->fine_precision_plan_ms,'
        'r->fine_precision_preparation_ms,r->fine_precision_execute_ms,'
        'r->fine_precision_storage_ms,r->fine_precision_score_ms,'
        'r->fine_precision_guard_ms,r->fine_precision_recompute_ms,'
        'r->fine_precision_free_ms,r->total_cpu_ms')
    receipt=json.loads((out/'fine-reuse-build.json').read_text())
    commands=[]
    for record in receipt['commands']:
        cmd=record['command']
        cmd=[arg.replace(str(BASE/baseline),str(out)) for arg in cmd]
        cmd=[str(out/'test_fine_precision.c') if arg.endswith('/test_fine_reuse.c') else arg for arg in cmd]
        cmd=[str(out/'test_fine_precision') if arg.endswith('/test_fine_reuse') else arg for arg in cmd]
        cmd=[str(out/'cohort_fine_precision') if arg.endswith('/cohort_fine_reuse') else arg for arg in cmd]
        if mode=='guarded': cmd.insert(1,'-DLEO_FINE_PRECISION_GUARDED=1')
        if sanitize:
            cmd=['-O1' if x=='-O3' else x for x in cmd]
            cmd[1:1]=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
            cmd.insert(-2,'-fsanitize=address,undefined')
        run=subprocess.run(cmd,capture_output=True,text=True,check=True)
        commands.append({'command':cmd,'compiler_stdout':run.stdout,'compiler_stderr':run.stderr})
    test=out/'test_fine_precision'
    if arm: unit_stdout='cross-build only; do not execute ARM workload here\n'; unit_stderr=''
    else:
        import os
        env=None if not sanitize else dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        run=subprocess.run([str(test)],capture_output=True,text=True,check=True,env=env)
        unit_stdout=run.stdout;unit_stderr=run.stderr
    binaries=[out/'cohort_fine_precision',test]
    result={'schema':'arm-fine-precision-build/v1','mode':mode,'arm':arm,'sanitize':sanitize,
        'source_baseline':str(BASE/baseline),'source_baseline_receipt_sha256':sha(BASE/baseline/'fine-reuse-build.json'),
        'guard':{'ulps':256.0,'tolerance':'256*FLT_EPSILON*max(1,abs(best_score))',
            'interpolation':'abs(curve)<=tolerance or abs(left-right)>=1.8*abs(curve) for negative curve',
            'claim':'conservative engineering screen; no universal error bound'},
        'commands':commands,'unit_stdout':unit_stdout,'unit_stderr':unit_stderr,
        'binaries':{p.name:sha(p) for p in binaries},
        'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'fine-precision-build.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'fine-reuse-build.json').unlink()

if __name__=='__main__': main()
