"""Root-approved six-job fresh regional sensitivity; no GPS in inference."""

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
RUNS=HERE/'position_runs'
CASES=('DS24-0011','DS24-0097')
VARIANTS=('baseline','additions_proxy','additions_bin_floor')
BIN=10000000/(44*512)


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def floored_noise(proxy,observation_ids,new_ids):
    noise=copy.deepcopy(proxy);selected=proxy['extra_parameter_BIC_gain']>0
    mapping={oid:proxy['per_observation_noise_sigma_hz'][oid] if selected else proxy['constant_radio_sigma_hz'] for oid in observation_ids}
    original=copy.deepcopy(mapping)
    for oid in new_ids:mapping[oid]=max(mapping[oid],BIN)
    noise['per_observation_noise_sigma_hz']=mapping
    noise.update(measured_extra_parameter_BIC_gain=proxy['extra_parameter_BIC_gain'],
        extra_parameter_BIC_gain=1.,extra_parameter_BIC_gain_is_activation_sentinel=True,
        research_override='Explicit per-ID scale selection; +1 is an activation sentinel, not a measured BIC gain',
        sensitivity_new_owner_sigma_floor_hz=BIN,new_uncertainty_calibrated=False)
    if any(mapping[oid]!=original[oid] for oid in observation_ids if oid not in new_ids):
        raise ValueError('floor changed incumbent scales')
    return noise


def prepare():
    RUNS.mkdir(exist_ok=False);inputs={};jobs=[]
    for case in CASES:
        ledger=read(HERE/(case+'_additions.json'));overlay=HERE/(case+'-additions-r01')
        graph=read(overlay/'graph_audit.json')
        if not graph['bank_support']['reuse_allowed']:raise ValueError('complete causal bank cannot be reused')
        original_rows=read(SOURCE/case/'observations.json');original_ids={o['observation_id'] for o in original_rows}
        new_ids={o['observation_id'] for o in ledger['observations']}-original_ids
        for variant in VARIANTS:
            root=RUNS/case/variant;folder=root/case;folder.mkdir(parents=True)
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
                shutil.copyfile(SOURCE/case/name,folder/name)
            prior=root/'causal_prior'/case;prior.mkdir(parents=True)
            for path in (SOURCE/'causal_prior'/case).iterdir():
                if path.is_file():shutil.copyfile(path,prior/path.name)
            history=root/'causal_phase_history';history.mkdir()
            for name in (case+'.json',case+'_forecast.json'):shutil.copyfile(SOURCE/'causal_phase_history'/name,history/name)
            if variant=='baseline':
                for name in ('observations.json','tracks.json','radio_noise.json'):shutil.copyfile(SOURCE/case/name,folder/name)
            else:
                for name in ('observations.json','tracks.json'):shutil.copyfile(overlay/name,folder/name)
                proxy=read(overlay/'radio_noise.json')
                if variant=='additions_bin_floor':
                    noise=floored_noise(proxy,[o['observation_id'] for o in ledger['observations']],new_ids)
                else:noise=proxy
                noise['source_sha256']={name:sha(folder/name) for name in ('observations.json','tracks.json')}
                noise['code_sha256']=sha(REPO/'tools/ds23_radio_noise.py')
                write(folder/'radio_noise.json',noise)
            prepared=read(SOURCE/case/'prepared.json')
            if variant!='baseline':
                prepared.update(GLRT_points=len(ledger['observations']),graph_points=graph['graph']['graph_points'],
                    graph_tracks=graph['graph']['graph_tracks'],curved_tracks=graph['graph']['curved_tracks'],
                    measurement_transfer='Research additions ledger + immutable original public export; unchanged later-sample confirmation scorer',
                    research_observation_ledger_sha256=sha(HERE/(case+'_additions.json')))
            write(folder/'prepared.json',prepared)
            # The historical input receipt still truthfully describes the unchanged
            # tracking export. This separate receipt is the authority for new rows.
            receipt=dict(schema='missed-visit-regional-research-input-v1',case=case,variant=variant,
                original_tracking_export_sha256=sha(SOURCE/case/'tracking.json'),tracking_export_unchanged=True,
                observation_source='unchanged public winners' if variant=='baseline' else 'independent additions-only research ledger',
                baseline_observation_sha256=sha(SOURCE/case/'observations.json'),
                added_native_observation_ids=[] if variant=='baseline' else sorted(new_ids),
                bank_support_audit=graph['bank_support'],GPS_used=False,
                c_arms=['c0','fitted_c'],regional_center=[37.906,-122.545],box_width_km=25.,start=[0.,0.],
                fresh_initialization=True,archived_results_or_discovery_nodes_copied=False)
            write(folder/'research_input_receipt.json',receipt)
            for path in root.rglob('*'):
                if path.is_file():inputs[str(path)]=sha(path)
            jobs.append(dict(case=case,variant=variant,root=str(root)))
    code={str(p):sha(p) for p in [Path(__file__),HERE/'position_harness/sitecustomize.py',HERE/'position_harness/position_read_audit.py',
        REPO/'tools/algo02_scan.py',SOURCE/'engine/ds24_engine.py',HERE/'POSITION_EXECUTION_PROPOSAL.md']}
    # All previously imported scientific Python sources remain hash-bound too.
    old=read(HERE/'baseline_source_receipt.json')['files_sha256']
    for path,digest in old.items():
        if sha(path)!=digest:raise ValueError('baseline source/input changed: '+path)
    write(HERE/'position_protocol.json',dict(schema='missed-visit-matched-regional-sensitivity-v1',
        frozen_utc_ns=time.time_ns(),cases=list(CASES),variants=list(VARIANTS),jobs=jobs,
        input_hashes=inputs,source_hashes=code,previous_baseline_source_receipt_sha256=sha(HERE/'baseline_source_receipt.json'),
        root_approved=True,seconds_per_complete_job=240,maximum_workers=2,BLAS_threads=1,
        radio_seed_budget=4,fully_fitted_RF_branches=3,phase_rounds=5,steps_per_round=48,
        original_gate_refit_and_cavity_limits=True,no_warm_starts=True,no_retries=True,
        GPS_in_inference=False,evaluation_permitted_after_all_terminal_seal_only=True,
        regional_center=[37.906,-122.545],box_width_km=25.,start=[0.,0.],
        one_bin_sensitivity_floor_hz=BIN,one_bin_floor_is_calibrated=False))
    print(json.dumps(dict(status='prepared_and_sealed',jobs=len(jobs),inputs=len(inputs))))


def run_job(job):
    root=Path(job['root']);case=job['case'];began=time.monotonic();deadline=began+240
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
        PYTHONPATH=':'.join(map(str,[HERE/'position_harness',Path('/tmp/algo03-feasible-deps'),REPO/'src',REPO/'tools',SOURCE/'engine'])),
        LEO_POSITION_RUN_ROOT=str(root),LEO_POSITION_AUDIT_DIR=str(root/'read_receipts'))
    result=dict(job,status='running',stages=[],GPS_in_inference=False)
    commands=[('fresh_algo02',[sys.executable,'-B',str(REPO/'tools/algo02_scan.py'),'--run-dir',str(root),'--case',case,'--stage','all']),
        ('signed_prior_equal_cavity',[sys.executable,'-B',str(SOURCE/'engine/ds24_engine.py'),'--root',str(root),'--case',case])]
    try:
        for stage,command in commands:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired(command,240)
            started=time.monotonic()
            with (root/(stage+'.log')).open('x') as log:
                process=subprocess.Popen(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    raise
            result['stages'].append(dict(stage=stage,returncode=code,seconds=time.monotonic()-started))
            write(root/(stage+'_checkpoint.json'),result['stages'][-1])
            if code:raise RuntimeError(stage+' failed; inspect retained log/read receipt')
        final=read(root/'family_cavity/position'/(case+'.json'))
        result['status']='complete' if final['status']=='complete' else 'inference_unavailable'
    except subprocess.TimeoutExpired:result.update(status='capped',reason='shared240scomplete-jobcap')
    except Exception as error:result.update(status='failed',error=repr(error))
    result['seconds']=time.monotonic()-began
    write(root/'execution.json',result)
    print(json.dumps(dict(case=case,variant=job['variant'],status=result['status'],seconds=result['seconds'])),flush=True)
    return result


def execute():
    active=HERE/'position_protocol_v2.json'
    protocol=read(active)
    for path,digest in dict(protocol['input_hashes'],**protocol['source_hashes']).items():
        if sha(path)!=digest:raise ValueError('sealed regional source/input changed: '+path)
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(run_job,job) for job in protocol['jobs']]):results.append(future.result())
    files={}
    denied=[]
    for job in protocol['jobs']:
        root=Path(job['root'])
        for path in root.rglob('*.json'):
            files[str(path)]=sha(path)
        for path in (root/'read_receipts').glob('*.json'):
            denied.extend(read(path)['denied_paths'])
    for path,digest in protocol['input_hashes'].items():
        if sha(path)!=digest:raise ValueError('regional inference changed sealed input: '+path)
    write(HERE/'position_terminal_seal.json',dict(all_terminal=True,results=results,
        protocol_sha256=sha(active),terminal_output_hashes=files,
        denied_reads=denied,GPS_error_evaluation_performed=False,
        inputs_unchanged=True,evaluation_now_permitted=not denied))
    print(json.dumps(dict(all_terminal=True,statuses=[r['status'] for r in results],denied_reads=len(denied))))


def reseal():
    original=read(HERE/'position_protocol.json')
    for path,digest in original['input_hashes'].items():
        if sha(path)!=digest:raise ValueError('prepared input changed before first inference')
    updated=copy.deepcopy(original)
    updated.update(frozen_utc_ns=time.time_ns(),previous_protocol_sha256=sha(HERE/'position_protocol.json'),
        pre_inference_amendment='Read-only import preflight exposed scientific-library dist-info under the established /tmp dependency symlink. Permit that library environment, retain all outcome/GPS guards. No inference job or scientific comparison had begun.')
    for path in updated['source_hashes']:updated['source_hashes'][path]=sha(path)
    updated['source_hashes'][str(HERE/'test_position_harness.py')]=sha(HERE/'test_position_harness.py')
    write(HERE/'position_protocol_v2.json',updated)
    print(json.dumps(dict(status='pre_inference_source_resealed',jobs=6,inputs_unchanged=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','reseal','run'));args=parser.parse_args()
    {'prepare':prepare,'reseal':reseal,'run':execute}[args.action]()
