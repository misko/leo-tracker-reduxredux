"""Bounded, resumable offline scan stages; no RF collection or QNAP writes."""
import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent


def command(stage, directory, variant=None):
    output=HERE/f'pilot-{directory.name}{"-seeded" if variant else ""}'
    model_directory=directory/variant if variant else directory
    if stage not in ('refine','bootstrap','seed'):
        directory=model_directory
    commands={
        'refine':['run_refinement.py',str(directory/'observations.json'),'--workers','2'],
        'bootstrap':['bootstrap_tracks.py',str(directory)],
        'seed':['seed_timing_variant.py',str(directory),'--variant-name',variant or 'seed-timing-v6'],
        'calibrate':['calibration.py',str(directory)],
        'discover':['discovery.py',str(directory),'--permit-calibration-warning'],
        'select':['select_associations.py',str(directory)],
        'plot':['plot_associations.py',str(directory),'--output',str(output)],
        'metrics':['render_pilot.py',str(directory),'--output',str(output)],
        'diagnostics':['track_diagnostics.py',str(directory),'--output',str(output)],
        'position':['run_fisher_positions.py',str(directory)],
        'curvature':['screen_curvature.py',str(directory.parent.parent),'--label',directory.parent.name],
        'prior':['screen_timing_priors.py',str(directory.parent.parent),'--label',directory.parent.name],
    }
    args=commands[stage]
    return [sys.executable,str(HERE/args[0]),*args[1:]]


def run_one(stage,directory,deadline,variant=None):
    terminal={'refine':'refinement/refined.json','bootstrap':'bootstrap.json',
              'discover':'discovery/candidate-pool.json','select':'selection-p10-g600-t1.json',
              'position':'position-fisher-v2/selection-p10-g600-t1/alternatives-support-100/summary.json'}
    # Do not repeat completed numerical work. Consumers still verify its source
    # signatures; this dispatcher does not claim to validate scientific results.
    artifact_directory=directory/variant if variant and stage not in ('refine','bootstrap','seed') else directory
    if stage in terminal and (artifact_directory/terminal[stage]).exists():
        return dict(scan=directory.name,stage=stage,status='existing_artifact_not_reexecuted')
    log=directory/f'batch-{stage}-{time.time_ns()}.log'
    started=time.monotonic()
    timeout=min(12*60,deadline-started)
    if timeout<30:
        return dict(scan=directory.name,stage=stage,status='batch_deadline_before_start')
    try:
        with log.open('x') as stream:
            process=subprocess.Popen(command(stage,directory,variant),stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Terminate this stage's private process group, including its
                # numerical workers. Never leave orphan writers on checkpoints.
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
                raise
        status='process_success' if process.returncode==0 else 'process_failed'
        code=process.returncode
    except subprocess.TimeoutExpired:
        # Refinement's per-visit checkpoints survive an interrupted stage.
        status,code='bounded_stage_timeout',None
    return dict(scan=directory.name,stage=stage,status=status,returncode=code,
                elapsed_s=time.monotonic()-started,log=str(log))


def run(inputs,labels,stages,workers=2,variant=None):
    cohort=json.loads((HERE/'cohort-v2.json').read_text())
    scans={s['label']:s for s in cohort['scans']}
    if variant is not None and ('/' in variant or not variant.startswith('seed-timing-')):
        raise ValueError('invalid variant name')
    if not 1<=len(labels)<=4 or not 1<=workers<=2 or len(set(labels))!=len(labels):
        raise ValueError('bounded batches allow 1–4 distinct scans and 1–2 concurrent stages')
    for label in labels:
        if label not in scans:
            raise ValueError('unknown scan')
        if any(s in ('prior','curvature') for s in stages) and (variant is None or scans[label]['split']!='development'):
            raise ValueError('prior/curvature screens require a versioned development scan')
        if scans[label]['split']=='locked_test' and any(s!='refine' for s in stages) and not (HERE/'final-settings.json').exists():
            raise ValueError('locked-test model outcomes must remain unopened until settings freeze')
        if scans[label]['split']=='locked_test' and any(s!='refine' for s in stages):
            from freeze_final_settings import read_freeze
            frozen=read_freeze(HERE)
            if variant!=frozen['variant']:raise ValueError('locked-test variant differs from frozen settings')
            if frozen['configuration']['name']!='baseline' and any(s in ('select','plot','metrics','diagnostics','position') for s in stages):
                raise ValueError('nonbaseline finalist requires its explicit selection file; default stage commands are baseline only')
    # Entire invocation may last at most 25 minutes; no unbounded campaign loop.
    deadline=time.monotonic()+25*60
    results=[]
    for stage in stages:
        remaining=deadline-time.monotonic()
        if remaining<30:
            break
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            tasks={pool.submit(run_one,stage,inputs/label,deadline,variant):label for label in labels}
            for future in concurrent.futures.as_completed(tasks):
                result=future.result()
                results.append(result)
                print(json.dumps(result),flush=True)
        failed={r['scan'] for r in results if r['stage']==stage and r['status'] in ('process_failed','bounded_stage_timeout','batch_deadline_before_start')}
        labels=[label for label in labels if label not in failed]
        if not labels:
            break
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',type=Path)
    p.add_argument('--labels',nargs='+',required=True)
    p.add_argument('--stages',nargs='+',choices=('refine','bootstrap','seed','calibrate','discover','select','plot','metrics','diagnostics','position','curvature','prior'),required=True)
    p.add_argument('--variant',help='Versioned timing initializer; raw input stages remain shared')
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    a=p.parse_args()
    run(a.inputs,a.labels,a.stages,a.workers,a.variant)
