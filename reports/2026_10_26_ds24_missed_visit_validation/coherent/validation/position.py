"""Four fresh regional jobs plus two equality-audited sealed controls."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import os
from pathlib import Path
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha,module
OLD=HERE.parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PREVIOUS=Path('/srv/bulk/leo/research/ds24-ch58-continuity-r01/validation')
BASE=module('sealed_sparse_position_mechanism',OLD/'position_run.py')
CASES=('DS24-0011','DS24-0097')
VARIANTS=('additions_proxy','additions_bin_floor')


def baseline_equality():
    protocol=read(OLD/'position_protocol_v2.json');terminal=read(OLD/'position_terminal_seal.json')
    assert terminal['all_terminal'] and terminal['inputs_unchanged'] and not terminal['denied_reads']
    assert terminal['protocol_sha256']==sha(OLD/'position_protocol_v2.json')
    for path,h in protocol['source_hashes'].items():assert sha(path)==h,path
    earlier=read(PREVIOUS/'source_receipt.json')['files_sha256']
    for path,h in earlier.items():assert sha(path)==h,path
    for path,h in read(OLD/'baseline_source_receipt.json')['files_sha256'].items():assert sha(path)==h,path
    controls=[]
    for case in CASES:
        job=next(j for j in protocol['jobs'] if j['case']==case and j['variant']=='baseline');root=Path(job['root'])
        expected=next(r for r in terminal['results'] if r['case']==case and r['variant']=='baseline')
        assert expected['status']=='complete'
        bound={p:h for p,h in protocol['input_hashes'].items() if Path(p).is_relative_to(root)}
        for path,h in bound.items():assert sha(path)==h,path
        compared=[]
        for name in ('tracking.json','input_receipt.json','observations.json','tracks.json','radio_noise.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
            assert sha(root/case/name)==sha(SOURCE/case/name),name
            compared.append(name)
        assert read(root/case/'prepared.json')==read(SOURCE/case/'prepared.json')
        for path in (root/'causal_prior'/case).iterdir():
            if path.is_file():assert sha(path)==sha(SOURCE/'causal_prior'/case/path.name)
        for name in (case+'.json',case+'_forecast.json'):assert sha(root/'causal_phase_history'/name)==sha(SOURCE/'causal_phase_history'/name)
        receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
        assert len(receipts)>=3 and not any(r['denied_paths'] for r in receipts)
        outputs={p:h for p,h in terminal['terminal_output_hashes'].items() if Path(p).is_relative_to(root)}
        # Integrity reads only: do not deserialize baseline endpoint values here.
        for path,h in outputs.items():assert sha(path)==h,path
        controls.append(dict(case=case,variant='baseline',root=str(root),status='verified_sealed_control',
            exact_input_files=compared,prepared_content_exact=True,causal_priors_and_phase_history_exact=True,
            input_hashes=bound,terminal_output_hashes=outputs,execution_sha256=sha(root/'execution.json'),
            no_denied_inference_reads=True,endpoint_values_opened=False))
    keys=('seconds_per_complete_job','maximum_workers','BLAS_threads','radio_seed_budget','fully_fitted_RF_branches',
        'phase_rounds','steps_per_round','regional_center','box_width_km','start')
    return dict(all_passed=True,controls=controls,reused_control_count=2,
        original_source_hashes=protocol['source_hashes'],prior_scientific_source_hashes=earlier,
        prior_imported_scientific_files_verified=len(earlier),baseline_source_receipt_sha256=sha(OLD/'baseline_source_receipt.json'),
        original_protocol_sha256=sha(OLD/'position_protocol_v2.json'),original_terminal_seal_sha256=sha(OLD/'position_terminal_seal.json'),
        settings={k:protocol[k] for k in keys},same_named_python_and_dependency_environment=True,
        environment_evidence='same .venv interpreter path and established dependency tree; all prior imported scientific source hashes unchanged',
        source_runtime_config_candidate_prior_budget_differences=[],baseline_endpoints_excluded_from_new_run_roots=True)


def prepare():
    equality=baseline_equality();write(HERE/'baseline_equality_audit.json',equality)
    runs=HERE/'position_runs';runs.mkdir(exist_ok=False);jobs=[];inputs={}
    for case in CASES:
        overlay=HERE/'graphs'/case;ledger=read(HERE/(case+'_additions.json'));graph=read(overlay/'graph_audit.json')
        assert graph['new_in_curved_graph']>0 and graph['bank_support']['reuse_allowed']
        original_ids={o['observation_id'] for o in read(SOURCE/case/'observations.json')}
        new={o['observation_id'] for o in ledger['observations']}-original_ids
        for variant in VARIANTS:
            root=runs/case/variant;folder=root/case;folder.mkdir(parents=True)
            for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
                shutil.copyfile(SOURCE/case/name,folder/name)
            prior=root/'causal_prior'/case;prior.mkdir(parents=True)
            for path in (SOURCE/'causal_prior'/case).iterdir():
                if path.is_file():shutil.copyfile(path,prior/path.name)
            history=root/'causal_phase_history';history.mkdir()
            for name in (case+'.json',case+'_forecast.json'):shutil.copyfile(SOURCE/'causal_phase_history'/name,history/name)
            for name in ('observations.json','tracks.json'):shutil.copyfile(overlay/name,folder/name)
            proxy=read(overlay/'radio_noise.json')
            noise=BASE.floored_noise(proxy,[o['observation_id'] for o in ledger['observations']],new) if variant=='additions_bin_floor' else proxy
            noise['source_sha256']={name:sha(folder/name) for name in ('observations.json','tracks.json')}
            noise['code_sha256']=sha(REPO/'tools/ds23_radio_noise.py');write(folder/'radio_noise.json',noise)
            prepared=read(SOURCE/case/'prepared.json')
            prepared.update(GLRT_points=len(ledger['observations']),graph_points=graph['graph']['graph_points'],
                graph_tracks=graph['graph']['graph_tracks'],curved_tracks=graph['graph']['curved_tracks'],
                measurement_transfer='Coherent expansion additions only + immutable original export',
                research_observation_ledger_sha256=sha(HERE/(case+'_additions.json')))
            write(folder/'prepared.json',prepared)
            write(folder/'research_input_receipt.json',dict(schema='missed-visit-regional-research-input-v1',case=case,variant=variant,
                original_tracking_export_sha256=sha(SOURCE/case/'tracking.json'),tracking_export_unchanged=True,
                observation_source='independent original-plus-coherent-expansion ledger; no sparse-only additions',
                added_native_observation_ids=sorted(new),baseline_observation_sha256=sha(SOURCE/case/'observations.json'),
                bank_support_audit=graph['bank_support'],GPS_used=False,c_arms=['c0','fitted_c'],
                regional_center=[37.906,-122.545],box_width_km=25.,start=[0.,0.],
                fresh_initialization=True,archived_results_or_discovery_nodes_copied=False))
            for path in root.rglob('*'):
                if path.is_file():inputs[str(path)]=sha(path)
            jobs.append(dict(case=case,variant=variant,root=str(root)))
    sources=dict(equality['original_source_hashes'])
    sources.update({str(p):sha(p) for p in [Path(__file__),HERE/'integrate.py',HERE/'graph.py',HERE/'test_integration.py',
        HERE/'POSITION_EXECUTION_PROPOSAL.md',HERE/'baseline_equality_audit.json',PREVIOUS/'source_receipt.json']})
    p=dict(schema='coherent-expansion-matched-regional-sensitivity/v1',frozen_utc_ns=time.time_ns(),
        cases=list(CASES),variants=['baseline',*VARIANTS],jobs=jobs,controls=equality['controls'],
        input_hashes=inputs,source_hashes=sources,requires_root_hash_authorization=True,
        baseline_equality_audit_sha256=sha(HERE/'baseline_equality_audit.json'),
        **equality['settings'],original_gate_refit_and_cavity_limits=True,no_warm_starts=True,no_retries=True,
        GPS_in_inference=False,evaluation_permitted_after_all_terminal_seal_only=True,
        one_bin_sensitivity_floor_hz=BASE.BIN,one_bin_floor_is_calibrated=False,
        same_c_arm_observations_candidates_priors_budgets=True,
        regional_initialization='unchanged ALGO02-v1 + qualified causal signed phase prior + equal-prior family cavity',
        control_endpoint_values_not_opened=True,baseline_endpoints_not_copied_to_inference=True)
    write(HERE/'position_protocol.json',p)
    print(dict(status='concrete_protocol_ready',protocol_sha256=sha(HERE/'position_protocol.json'),new_jobs=len(jobs),reused_controls=2,input_files=len(inputs)),flush=True)


def run():
    p=read(HERE/'position_protocol.json');auth=read(HERE/'position_run_authorization.json')
    assert auth['protocol_sha256']==sha(HERE/'position_protocol.json') and auth['position_execution_authorized']
    for path,h in dict(p['input_hashes'],**p['source_hashes']).items():assert sha(path)==h,path
    for path,h in read(HERE/'baseline_equality_audit.json')['prior_scientific_source_hashes'].items():assert sha(path)==h,path
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(BASE.run_job,j) for j in p['jobs']]):results.append(future.result())
    files={};denied=[]
    for job in p['jobs']:
        root=Path(job['root'])
        for path in root.rglob('*.json'):files[str(path)]=sha(path)
        for path in (root/'read_receipts').glob('*.json'):denied.extend(read(path)['denied_paths'])
    for path,h in p['input_hashes'].items():assert sha(path)==h,path
    write(HERE/'position_terminal_seal.json',dict(all_terminal=True,results=results,
        protocol_sha256=sha(HERE/'position_protocol.json'),authorization_sha256=sha(HERE/'position_run_authorization.json'),
        terminal_output_hashes=files,denied_reads=denied,GPS_error_evaluation_performed=False,
        inputs_unchanged=True,evaluation_now_permitted=not denied,reused_controls=p['controls']))
    print(dict(all_terminal=True,statuses=[r['status'] for r in results],denied_reads=len(denied)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);a=parser.parse_args()
    {'prepare':prepare,'run':run}[a.action]()
