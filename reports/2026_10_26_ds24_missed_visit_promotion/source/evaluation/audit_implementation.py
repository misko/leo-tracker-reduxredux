"""Independent pre-geography source/native-input audit; no endpoint reads."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OLD=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation')
sys.path.insert(0,str(OLD))
from baseline_scope import metadata_inventory


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def audit_protocol(path):
    path=Path(path);p=read(path);began=time.monotonic();evaluation=read(HERE/'protocol_v2.json')
    assert p['cases']==evaluation['held_cases']
    sources=p.get('sources_sha256',p.get('source_hashes',{}));inputs=p.get('inputs_sha256',p.get('input_hashes',{}))
    for name,h in dict(sources,**inputs).items():assert sha(name)==h,name
    assert p['regional_center']==[37.906,-122.545] and p['box_width_km']==25. and p['start']==[0.,0.]
    assert p.get('seconds_per_job',p.get('seconds_per_complete_job'))==240
    assert p['maximum_workers']<=4 and p['BLAS_threads']==1 and p['uid']==1000
    assert p['radio_seed_budget']==4 and p['fully_fitted_RF_branches']==3 and p['phase_rounds']==5 and p['steps_per_round']==48
    assert p['full_causal_catalogue'] and p['causal_signed_prior'] and p['equal_prior_family_cavity']
    assert p['no_GPS_inference'] and p['no_archived_endpoint_input']
    identity_path=path.parent/'module_identity_audit.json';identity=read(identity_path) if identity_path.exists() else None
    actual_matches=[]
    if identity:
        prior=read('/srv/bulk/leo/research/ds24-ch58-continuity-r01/validation/source_receipt.json')['files_sha256']
        modules=identity['modules'];assert modules['leo']['path']==str(REPO/'src/leo/__init__.py')
        for name,entry in modules.items():
            file=entry['path'];assert sha(file)==entry['sha256'],file
            assert not file.startswith('/opt/leo-shared-scans/'),file
            if file in prior:assert entry['sha256']==prior[file],file;actual_matches.append(name)
        assert modules['leo.analysis.research.retained_track_likelihood']['path'].startswith(str(REPO/'src')+'/')
        assert modules['leo.analysis.research.orbit_phase_geometry']['path'].startswith(str(REPO/'src')+'/')
        for file,h in identity['additional_frozen_unused_native_extensions'].items():
            assert file.endswith('_native_acquisition.cpython-312-x86_64-linux-gnu.so') and sha(file)==h
    inventories={};audits=[]
    for job in p['jobs']:
        case=job['case'];variant=job['variant'];root=Path(job['root']);folder=root/case
        if case not in inventories:inventories[case]=metadata_inventory(case)
        tracking,native,original=inventories[case];byid={n['observation_id']:n for n in native}
        rows=read(folder/'observations.json');ids=[o['observation_id'] for o in rows]
        assert len(ids)==len(set(ids)) and rows[:len(original)]==original
        new=set(ids)-{r['observation_id'] for r in original}
        receipt=read(folder/'research_input_receipt.json');assert set(receipt['added_native_observation_ids'])==new
        if variant=='baseline':assert not new and rows==original
        for row in rows:
            n=byid[row['observation_id']]
            assert all(row[k]==n[k] for k in ('receiver','native_receiver_id','channel','actual_rf_hz','time_s'))
        for name in ('tracking.json','input_receipt.json','bank.npz','nominal_elements.json','receipt.json','selected.tle','previous.tle','previous_receipt.json'):
            assert sha(folder/name)==sha(SOURCE/case/name),name
        for source in (SOURCE/'causal_prior'/case).iterdir():
            if source.is_file():assert sha(root/'causal_prior'/case/source.name)==sha(source)
        causal=read(root/'causal_prior'/case/'receipt.json');previous=read(root/'causal_prior'/case/'previous_receipt.json')
        assert causal['reference_position_used'] is False and causal['cutoff_utc_ns']<=causal['origin_utc_ns']
        assert causal['search_center']==[37.906,-122.545] and causal['search_box_width_km']==25.
        for entry in previous['sources'].values():assert entry['epoch_utc_ns']<=causal['cutoff_utc_ns'] and entry['collected_utc_ns']<=causal['cutoff_utc_ns']
        for name in (case+'.json',case+'_forecast.json'):assert sha(root/'causal_phase_history'/name)==sha(SOURCE/'causal_phase_history'/name)
        graph=read(folder/'tracks.json');graph_ids=[oid for t in graph for oid in t['observation_ids']]
        assert len(graph_ids)==len(set(graph_ids)) and set(graph_ids)<=set(ids)
        noise=read(folder/'radio_noise.json')
        audits.append(dict(case=case,variant=variant,root=str(root),original_GLRT_count=len(original),total_GLRT_count=len(rows),
            new_native=len(new),original_rows_exact=True,native_bindings_verified=len(rows),graph_unique_native_owners=True,
            original_candidate_bank_and_causal_priors_exact=True,new_native_ids=sorted(new),
            noise_scale_selection='per_observation' if noise['extra_parameter_BIC_gain']>0 else 'constant',
            no_endpoint_or_GPS_reads=True))
    return dict(all_passed=True,implementation_protocol=str(path),implementation_protocol_sha256=sha(path),
        evaluation_protocol_sha256=sha(HERE/'protocol_v2.json'),source_files_verified=len(sources),input_files_verified=len(inputs),
        actual_module_receipt=str(identity_path) if identity else None,actual_module_receipt_sha256=sha(identity_path) if identity else None,
        actual_loaded_modules_matching_prior_source_receipt=len(actual_matches),jobs=audits,
        primary_candidate_inputs_ready=any(j['variant']!='baseline' for j in p['jobs']),
        baseline_only_protocol_is_not_primary_candidate_evidence=all(j['variant']=='baseline' for j in p['jobs']),
        geography_opened=False,numerical_fit_calls=0,IQ_calls=0,seconds=time.monotonic()-began)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--protocol',type=Path,required=True);parser.add_argument('--name',required=True);args=parser.parse_args()
    assert Path(args.name).name==args.name
    result=audit_protocol(args.protocol);write(HERE/(args.name+'.json'),result)
    print({k:v for k,v in result.items() if k!='jobs'})
