"""Run every distinct expanded-ranking winner through the production worker."""
import hashlib,json,subprocess
from pathlib import Path
from tests.starlink_glrt.test_tracking_seed import SOURCES
BASE=Path(__file__).parent
FW=Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking')
PREFIX=Path('/srv/bulk/leo/glrt-deployment-20260909/fftw-host-v1/install')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=BASE/'expanded-worker-v1';out.mkdir(exist_ok=False)
names=['glrt_cpu_coarse.c','glrt_cpu_seed.c','glrt_tracking_worker.c','glrt_tracking_live_bootstrap.c','glrt_tracking_iq.c',*SOURCES]
command=['cc','-std=c99','-O3','-Wall','-Wextra','-Werror','-pthread','-I',str(PREFIX/'include'),str(BASE/'expanded_worker_bench.c'),*(str(FW/'tools'/n) for n in names),'-L',str(PREFIX/'lib'),'-Wl,-rpath,'+str(PREFIX/'lib'),'-lfftw3','-lm','-o',str(out/'bench')]
subprocess.run(command,check=True)
source=BASE/'expanded-proposal-ranking-v1.json';ranking=json.loads(source.read_text())
prior=json.loads((BASE/'combined-pilot-controls-v1/result.json').read_text())
result=dict(new_rf_samples=0,receiver_time='frozen',acquisition_qualified=False,compile_command=command,
    ranking_sha256=digest(source),binary_sha256=digest(out/'bench'),runner_sha256=digest(Path(__file__)),
    bench_source_sha256=digest(BASE/'expanded_worker_bench.c'),references_sha256=digest(BASE/'direct-references.ci16'),
    production_source_sha256={n:digest(FW/'tools'/n) for n in [*names,'glrt_cpu_tracking_bench.c']},cases=[])
for case,original in zip(ranking['cases'],prior['cases']):
    assert (case['label'],case['number'])==(original['label'],original['number'])
    path=BASE/'combined-pilot-controls-v1'/f"{case['label']}-{case['number']}"/'iq.ci16'
    assert digest(path)==original['input_sha256']
    winners=sorted({b[k+'_winner'] for b in case['budgets'] for k in ('single','four')})
    runs={}
    for index in winners:
        peak=case['scores'][index-1]
        run=subprocess.run([str(out/'bench'),str(path),str(BASE/'direct-references.ci16'),str(peak['epoch']),str(peak['frequency']),str(peak['coarse_score'])],capture_output=True,timeout=12)
        journal=out/f"{case['label']}-{case['number']}-{index}.jsonl"
        journal.write_bytes(run.stdout);assert not run.stderr;run.check_returncode()
        rows=[json.loads(line) for line in run.stdout.splitlines()];past=[r for r in rows if r['kind']==3]
        assert rows[-1]['kind']=='terminal' and len(past)==rows[-1]['retained_past']
        runs[index]=dict(terminal=rows[-1],accepted=sum(r['accepted'] for r in past),journal_sha256=digest(journal))
    budgets=[dict(budget=b['budget'],**{k:dict(winner=b[k+'_winner'],**runs[b[k+'_winner']]) for k in ('single','four')}) for b in case['budgets']]
    result['cases'].append(dict(label=case['label'],number=case['number'],input_sha256=digest(path),runs=runs,budgets=budgets))
    print(case['label'],case['number'],[(b['budget'],b['single']['accepted'],b['four']['accepted']) for b in budgets],flush=True)
with (out/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
