"""Frozen tracking algorithms on identical cutoff-disabled GLRT observations."""
import argparse
import json
from pathlib import Path
import shlex
import statistics
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
OLD=REPORTS/'2026_09_30_arm_streaming_tracks'
NEW=REPORTS/'2026_10_01_arm_ungated_full_scan'
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
INPUT=NEW/'analysis/observations.tsv'
sys.path.insert(0,str(OLD))
from evaluate import fit_quality
from run_device import SSH,AUTH,OPTIONS,WRAPPER
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m

HYBRID=REPORTS/'2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts'
COARSE=REPORTS/'2026_09_30_arm_fast_tracks/grid'
METHODS={
    'rolling':(OLD/'rolling/artifacts','leo-streaming-rolling','test-streaming-rolling-arm'),
    'kalman-v2':(OLD/'kalman-v2/artifacts','leo-streaming-kalman-v2','test-streaming-kalman-v2-arm'),
    'linking-v2':(OLD/'linking-v2/artifacts','leo-local-tracklet-linking-v2','test-local-tracklet-linking-v2-arm'),
    'coarse-seeded':(HYBRID,'leo-curvature-tracks','test-curvature-tracks-arm')}
REMOTE='/mnt/glrtbench/ungated-tracker-comparison-20261001'

def run(argv,timeout=150):
    return subprocess.run(list(map(str,argv)),text=True,capture_output=True,check=True,timeout=timeout)

def elapsed(stderr):
    extension=next(float(l.split('\t')[2]) for l in stderr.splitlines() if l.startswith('TIMING\treconstruct_s\t'))
    objects=[json.loads(l) for l in stderr.splitlines() if l.startswith('{')]
    return extension+sum(d['reconstruct_s'] for d in objects if 'reconstruct_s' in d)

def host():
    for name,(folder,binary,_) in METHODS.items():
        out=HERE/name;out.mkdir(exist_ok=False)
        timings=[]
        for i in range(3):
            stderr='';args=[folder/binary,INPUT]
            if name=='coarse-seeded':
                seed=run([COARSE/'grid-trial-v3',INPUT,151,8,512,8,4,16])
                (out/f'seeds-{i}.tsv').write_text(seed.stdout);stderr+=seed.stderr
                args+=['--acceleration',250,'--seeds',out/f'seeds-{i}.tsv']
            result=run(args);stderr+=result.stderr
            (out/f'tracks-{i}.tsv').write_text(result.stdout);(out/f'tracks-{i}.stderr').write_text(stderr)
            timings.append(elapsed(stderr))
        assert len({m.digest(out/f'tracks-{i}.tsv') for i in range(3)})==1
        if name=='coarse-seeded':assert len({m.digest(out/f'seeds-{i}.tsv') for i in range(3)})==1
        receipt={'binary_sha256':m.digest(folder/binary),'input_sha256':m.digest(INPUT),'tracking_times_s':timings,
                 'all_repetitions_identical':True}
        if name=='coarse-seeded':receipt['coarse_binary_sha256']=m.digest(COARSE/'grid-trial-v3')
        (out/'host-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(name,'host median',statistics.median(timings),flush=True)

def score():
    so=m.read_observations(BASE/'server-observations.tsv');ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    obs=m.read_observations(INPUT);sources=m.read_sources(NEW/'analysis/candidate-map.tsv',obs)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so)
    settings=json.loads((REPORTS/'2026_09_30_arm_curvature_tracks/evaluation/thresholds.json').read_text())
    rows=[]
    paths={name:HERE/name/'tracks-0.tsv' for name in METHODS}
    paths['rolling-backfill']=NEW/'analysis/tracks-0.tsv'
    for name,path in paths.items():
        out=HERE/name;out.mkdir(exist_ok=True)
        tracks=m.read_tracks(path,obs)
        evaluation=m.compare(refs,tracks,so,obs,ss,sources,settings)
        represented=set(evaluation['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
        coverage=set();best={};supported=set()
        for ref in refs.values:
            metrics=[(m.membership_metrics(ref,t,so,obs,ss,sources,settings),t.index) for t in tracks.values if t.lane==ref.lane]
            if not metrics:continue
            for met,index in metrics:
                if met['consistent_source_count']:supported.add(index)
            met,index=max(metrics,key=lambda x:(m.complete(x[0],settings),x[0]['consistent_source_count'],x[0]['in_span_output_purity']))
            best[str(ref.index)]={'output_index':index,**met}
            if met['reference_source_coverage']>=.8 and ref.index!=10:coverage.add(ref.index)
        evaluation['fit_quality']=fit_quality(tracks,obs)
        evaluation['reviewed']={'represented':len(represented),'indexes':sorted(represented),'excluded':[10],
            'coverage_only_count':len(coverage),'coverage_only_indexes':sorted(coverage),
            'coverage_only_warning':'Diagnostic only: ignores source purity and does not establish correct identity'}
        (out/'evaluation.json').write_text(json.dumps(evaluation,indent=2)+'\n')
        (out/'best-per-reference.json').write_text(json.dumps(best,indent=2)+'\n')
        buckets={}
        for label,lo,hi in [('short',0,15),('medium',15,30),('long',30,float('inf'))]:
            ids={r.index for r in refs.values if r.index!=10 and lo<=(r.end_ns-r.start_ns)/1e9<hi}
            buckets[label]={'matched':len(ids&represented),'denominator':len(ids),'coverage_only':len(ids&coverage)}
        rows.append({'method':name,'strict':len(represented),'coverage_only':len(coverage),'duration_buckets':buckets,
            'strict_indexes':sorted(represented),'missing':sorted(set(range(63))-{10}-represented),
            'hypotheses':len(tracks.values),'without_reference_support':len(tracks.values)-len(supported),
            'prediction_p95_hz':evaluation['fit_quality']['p95_hz'],
            'regression_targets':{str(i):{'strict':i in represented,'matching_sources':best[str(i)]['consistent_source_count'],
                'reference_sources':best[str(i)]['reference_source_count'],'purity':best[str(i)]['in_span_output_purity']} for i in [9,19,33,37]}})
        print(name,rows[-1]['strict'],rows[-1]['coverage_only'],len(tracks.values),flush=True)
    (HERE/'science-summary.json').write_text(json.dumps(rows,indent=2)+'\n')

def device():
    run(SSH+['mkdir '+REMOTE])
    run(AUTH+['scp','-O']+OPTIONS+[INPUT,f'root@192.168.1.15:{REMOTE}/observations.tsv'])
    assert run(SSH+[f'sha256sum {REMOTE}/observations.tsv']).stdout.split()[0]==m.digest(INPUT)
    for name,(folder,binary,unit) in METHODS.items():
        out=HERE/name/'device';out.mkdir(exist_ok=False)
        for label,path in [('cli',folder/(binary+'-arm')),('unit',folder/unit)]:
            remote=f'{REMOTE}/{name}-{label}'
            run(AUTH+['scp','-O']+OPTIONS+[path,f'root@192.168.1.15:{remote}'])
            assert run(SSH+[f'chmod 755 {remote}; sha256sum {remote}']).stdout.split()[0]==m.digest(path)
        unit_result=run(SSH+[f'{WRAPPER} 90 {REMOTE}/{name}-unit'])
        (out/'unit.stdout').write_text(unit_result.stdout);(out/'unit.stderr').write_text(unit_result.stderr)
        if name=='coarse-seeded':
            coarse='/mnt/glrtbench/fast-tracks-f363-v1/grid-trial-arm-v3'
            assert run(SSH+['sha256sum '+coarse]).stdout.split()[0]==m.digest(COARSE/'grid-trial-arm-v3')
        trials=[]
        for i in range(3):
            command=f'{REMOTE}/{name}-cli {REMOTE}/observations.tsv'
            if name=='coarse-seeded':
                command=(f'{coarse} {REMOTE}/observations.tsv 151 8 512 8 4 16 > {REMOTE}/seeds.tsv && '
                         f'{command} --acceleration 250 --seeds {REMOTE}/seeds.tsv')
            result=run(SSH+[f'{WRAPPER} 90 /bin/sh -c '+shlex.quote(command)])
            (out/f'tracks-{i}.tsv').write_text(result.stdout);(out/f'tracks-{i}.stderr').write_text(result.stderr)
            equal=m.digest(out/f'tracks-{i}.tsv')==m.digest(HERE/name/'tracks-0.tsv');assert equal
            if name=='coarse-seeded':assert run(SSH+[f'sha256sum {REMOTE}/seeds.tsv']).stdout.split()[0]==m.digest(HERE/name/'seeds-0.tsv')
            whole=next(json.loads(l) for l in result.stderr.splitlines() if l.startswith('{') and json.loads(l).get('scope')=='whole_process')
            trials.append({'tracking_s':elapsed(result.stderr),'whole':whole,'host_byte_identical':equal})
        receipt={'trials':trials,'median_tracking_s':statistics.median(t['tracking_s'] for t in trials),
                 'binary_sha256':m.digest(folder/(binary+'-arm')),'unit_pass':True,'input_sha256':m.digest(INPUT)}
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(name,'ARM median',receipt['median_tracking_s'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['host','score','device']);args=p.parse_args()
    globals()[args.phase]()
