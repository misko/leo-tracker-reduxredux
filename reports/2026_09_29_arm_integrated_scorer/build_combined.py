"""Compose direct CI16 with fine and conditioned frame budgets."""
import hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
FRAME=HERE.parent/'2026_09_29_arm_frame_budget'
CONDITIONED=FRAME/'sources'/'conditioned-frame-budget'
FINE=FRAME/'sources'/'frame-budget'
spec=importlib.util.spec_from_file_location('direct_build',HERE/'build.py')
direct=importlib.util.module_from_spec(spec);spec.loader.exec_module(direct)
direct.BASE=CONDITIONED
BUDGETS=(1,2,4)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise RuntimeError(f'{path}: count={text.count(old)} for {old[:50]!r}')
    path.write_text(text.replace(old,new))

def prepare(out):
    direct.prepare(out)
    shutil.copy2(FINE/'fine_precision.h',out/'fine_precision.h')
    shutil.copy2(FINE/'test_fine_precision.c',out/'test_fine_precision.c')
    cohort=out/'cohort_probe.c'
    once(cohort,'\\"fine_precision_mode\\":\\"raw\\",\\"fine_precision_calls\\":%d',
         '\\"fine_precision_mode\\":\\"raw\\",\\"fine_frame_budget\\":%d,\\"conditioned_frame_budget\\":%d,\\"fine_precision_calls\\":%d')
    once(cohort,'r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->fine_precision_calls',
         'r->fine_fft_cache_entries,r->fine_fft_cache_hits,leo_fine_precision_frame_budget,conditioned_frame_budget(),r->fine_precision_calls')
    once(cohort,'    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);','''    const char *budget_text=getenv("LEO_FINE_FRAME_BUDGET");
    if(budget_text) {
        char *budget_end; errno=0; long budget=strtol(budget_text,&budget_end,10);
        if(errno || *budget_end || leo_fine_precision_set_frame_budget((int)budget)) return 2;
    }
    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);''')

def command(out,target,source,name,fine=None,conditioned=None):
    cmd=direct.command(out,target,source,name)
    at=cmd.index('-DLEO_PRESENCE_FFTW=1')+1
    flags=[]
    if fine is not None:flags.append(f'-DLEO_FINE_FRAME_BUDGET_DEFAULT={fine}')
    if conditioned is not None:flags.append(f'-DLEO_CONDITIONED_FRAME_BUDGET_DEFAULT={conditioned}')
    cmd[at:at]=flags
    return cmd

def build(target):
    out=HERE/'builds-combined'/f'{target}-v1'
    if out.exists():raise SystemExit(f'refusing overwrite {out}')
    prepare(out);records=[];binaries=[]
    for fine in BUDGETS:
        for conditioned in BUDGETS:
            name=f'cohort_integrated_f{fine}_c{conditioned}'
            cmd=command(out,target,'cohort_probe.c',name,fine,conditioned)
            run=subprocess.run(cmd,text=True,capture_output=True,check=True)
            records.append({'fine_budget':fine,'conditioned_budget':conditioned,'command':cmd,'stdout':run.stdout,'stderr':run.stderr})
            binaries.append(out/name)
    tests=[]
    for source,name in [('test_fine_precision.c','test_fine_precision'),('test_direct_glrt.c','test_conditioned_budget'),('test_ci16_integration.c','test_ci16_integration')]:
        cmd=command(out,target,source,name)
        run=subprocess.run(cmd,text=True,capture_output=True,check=True)
        records.append({'command':cmd,'stdout':run.stdout,'stderr':run.stderr});binaries.append(out/name)
        if target=='host':
            test=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            tests.append({'binary':name,'stdout':test.stdout,'stderr':test.stderr})
    receipt={'schema':'arm-integrated-budget-scorer-build/v1','target':target,
      'baselines':{'conditioned_source':str(CONDITIONED),'conditioned_receipt_sha256':sha(FRAME/'builds-conditioned'/target/'build-receipt.json'),'fine_source':str(FINE),'fine_receipt_sha256':sha(FRAME/'builds'/target/'build-receipt.json'),'direct_ci16_receipt_sha256':sha(HERE/'builds'/f'{target}-v3'/'build-receipt.json')},
      'runtime_configuration':{'fine_environment':'LEO_FINE_FRAME_BUDGET','conditioned_environment':'LEO_CONDITIONED_FRAME_BUDGET','allowed':[1,2,4,8],'compiled_matrix':[{'fine':f,'conditioned':c} for f in BUDGETS for c in BUDGETS]},
      'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    for target in ('host','arm'):build(target)
