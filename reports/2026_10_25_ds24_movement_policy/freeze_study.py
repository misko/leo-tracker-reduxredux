"""Read-only source inventory and coordinator freeze; no scientific fits."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
FULL = Path('/srv/bulk/leo/research/ds25-20261024')
CONTROLS = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
PLAN = REPO/'plans/ds24-movement-execution-plan.md'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return dict(path=str(path), sha256=sha(path), bytes=Path(path).stat().st_size)


def write(name, value):
    with (HERE/name).open('x') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def main():
    for name in ('cohort_ledger.json', 'preflight.json', 'protocol.json'):
        if (HERE/name).exists():
            raise FileExistsError('Preserve frozen coordinator artifact: '+name)
    manifest = Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json')
    authorities = [manifest, FULL/'sample.json', FULL/'execution.json',
                   CONTROLS/'receiver/protocol.json', PLAN, Path(__file__)]
    sample = read(FULL/'sample.json')
    members = {r['recording_id']: r for r in read(manifest)['members']}
    execution = {r['case']: r for r in read(FULL/'execution.json')['receipts']}
    eligible = read(CONTROLS/'receiver/protocol.json')['cases']
    fast = sorted((r for r in sample['selected'] if r['mode']=='fast'),
                  key=lambda r:(r['captured_utc_ns'], r['dataset_label']))
    assert len(fast)==34 and len(eligible)==24
    rows=[]
    for item in fast:
        case=item['dataset_label']; original=members[item['recording_id']]
        assert original['raw_authority_digest']==item['raw_authority_digest']
        assert original['captured_utc_ns']==item['captured_utc_ns']
        selected=case in eligible
        row=dict(case=case, recording_id=item['recording_id'],
                 session_id=item['session_id'], session_ids=item['session_ids'],
                 captured_utc_ns=item['captured_utc_ns'], mode='fast',
                 sample_rate_hz=item['sample_rate_hz'], raw_authority_digest=item['raw_authority_digest'],
                 raw_identity_sha256=item.get('raw_identity_sha256'),
                 inherited_tracking_authorities=item['tracking_inputs'],
                 dataset_parent_case=original['dataset_label'],
                 eligible=selected, frozen_execution_status=execution[case]['status'],
                 frozen_reason=execution[case].get('reason'),
                 exposure='previously examined same-site development',
                 selected_development_example=case in ('DS24-0017','DS24-0095'))
        if selected:
            paths=[FULL/'family_cavity/position'/f'{case}.json',
                   CONTROLS/'evaluation/models/receiver_fast_rx1_rf50'/f'{case}.json']
            row['baseline']=bind(paths[0]); row['existing_rx1']=bind(paths[1])
            row['frozen_scan_files']=[bind(FULL/case/name) for name in
                ('tracking.json','input_receipt.json','observations.json','tracks.json',
                 'bank.npz','selected.tle','previous.tle','previous_receipt.json',
                 'nominal_elements.json','receipt.json','prepared.json','radio_noise.json')]
            assert execution[case]['status']=='complete'
        else:
            assert execution[case]['status']=='input_unqualified'
            assert execution[case]['reason']=='input_unavailable'
        rows.append(row)
    ordered=[r['case'] for r in rows if r['eligible']]
    assert set(ordered)==set(eligible)
    assert {r['case'] for r in rows if not r['eligible']} == {
        *(f'DS24-{i:04d}' for i in range(1,10)), 'DS24-0103'}
    ledger=dict(schema='ds24-movement-study-cohort/v1', population=34, eligible_count=24,
                unavailable_count=10, interpretation='frozen input availability, not current raw-IQ availability',
                authorities=[bind(p) for p in authorities], eligible_cases=ordered, rows=rows)
    write('cohort_ledger.json',ledger)
    memory={line.split(':')[0]:int(line.split()[1])*1024
            for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=3}
    preflight=dict(utc=datetime.now(timezone.utc).isoformat(), cpu_count=os.cpu_count(),
        affinity_cpu_count=len(os.sched_getaffinity(0)), loadavg=list(os.getloadavg()),
        memory_available_bytes=memory['MemAvailable'], memory_total_bytes=memory['MemTotal'],
        disk=shutil.disk_usage(HERE)._asdict(), allocated_cpu_capacity=8,
        cpu_allocation_basis='24 logical CPUs and preflight load below16; capped8 across this study',
        working_git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        tracked_status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=no'],cwd=REPO,text=True),
        tracked_diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff','--binary','HEAD'],cwd=REPO)).hexdigest())
    assert preflight['affinity_cpu_count']>=8 and max(preflight['loadavg'])<16
    assert preflight['memory_available_bytes']>8*1024**3
    assert preflight['disk']['free']>10*1024**3
    write('preflight.json',preflight)
    seeds=[2026102504,2026102505]
    jobs=[dict(case=c,seed=s,fold=f) for c in ordered for s in seeds for f in range(3)]
    protocol=dict(schema='ds24-movement-study/v1', created_utc=datetime.now(timezone.utc).isoformat(),
        plan=bind(PLAN),cohort=bind(HERE/'cohort_ledger.json'),preflight=bind(HERE/'preflight.json'),
        scientific_inference_uses_GPS=False, no_new_RF=True, causal_only=True,
        region_center_latlon=[37.906,-122.545],region_width_km=25,
        cases=ordered,seeds=seeds,job_dispatch=jobs,smoke_jobs=jobs[:2],
        expected_counts=dict(fold_jobs=144,train_position_fits=576,crossover_vectors=1152,noise_scores=3456),
        recovery_cases=['DS24-0095','DS24-0087'],
        resources=dict(start_workers=2,max_movement_workers=6,recovery_workers=1,audit_workers=1,
            global_cpu_heavy_processes=8,blas_threads=1,per_fold_seconds=240,batch_wall_seconds=2700,
            recovery_pilot_seconds=1800,
            expansion_rule='six times max smoke peak RSS < half preflight memory_available_bytes; allocated_cpu_capacity>=8'),
        execution_gate='independent source/protocol/test audit and coordinator go receipt before scientific jobs',
        evaluation_gate='all scientific outputs and RF-only policy decisions sealed before geographic evaluation',
        promotion='none automatic; development replication only')
    write('protocol.json',protocol)
    print(json.dumps(dict(status='frozen',cases=ordered,population=34,eligible=24,jobs=len(jobs),
                          root=str(HERE),protocol_sha256=sha(HERE/'protocol.json'))))


if __name__=='__main__':
    main()
