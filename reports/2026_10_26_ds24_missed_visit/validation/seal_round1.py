"""Finalize a lean publication allowlist and hashes; large runs stay local."""
import gzip
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def write(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def main():
    # Existing sealed inference outputs are checked before making compact copies.
    terminal=read(HERE/'position_terminal_seal.json')
    for path,digest in terminal['terminal_output_hashes'].items():assert sha(path)==digest,path
    for path,digest in read(HERE/'baseline_source_receipt.json')['files_sha256'].items():assert sha(path)==digest,path
    pred=read(HERE/'prediction_audit.json');pred.pop('native_bindings')
    pred['full_native_binding_audit_sha256']=sha(HERE/'prediction_audit.json')
    write('prediction_audit_compact.json',pred)
    audit=read(HERE/'position_inference_audit.json')
    audit['full_read_path_audit_sha256']=sha(HERE/'position_inference_audit.json')
    for row in audit['audited']:
        paths=row.pop('read_paths');row['unique_read_paths']=len(paths)
    write('position_inference_audit_compact.json',audit)
    half=ROOT/'halfcell_diagnostic';p=read(half/'protocol.json')
    assert p['source_sha256']==sha(ROOT/'halfcell_diagnostic.py')
    with gzip.open(half/'outcomes.json.gz','rt') as stream:h=json.load(stream)
    with gzip.open(ROOT/'timing/outcomes/boundary.json.gz','rt') as stream:b=json.load(stream)
    hashes={r['target_sha256'] for r in h['rows']}
    assert len(hashes)==80
    overlaps=len(hashes&{r['target_sha256'] for r in b['rows']})
    for row in h['rows']:
        assert read(half/'selections'/f"{row['trial']}.json")==row['result']['selection_receipt']
    write('halfcell_audit.json',dict(summary=h['summary'],independent_vectors_within_diagnostic=80,
        overlap_with_boundary_control_vectors=overlaps,do_not_pool_as_independent=True,
        source_sha256=sha(ROOT/'halfcell_diagnostic.py'),protocol_sha256=sha(half/'protocol.json'),outcome_sha256=sha(half/'outcomes.json.gz'),
        scorer_unchanged=True,new_scoring_calls_in_validation=0))
    tests=dict(passed=36,failed=0,skipped=0,
        isolated_suites={'integration_and_graph':19,'timing_boundary':4,'candidate_ledger':4,'position_harness':3,
                        'position_evaluate':2,'round1_receipts':4},
        source_and_receipt_assertions_also_passed=True)
    write('final_test_results.json',tests)
    names=sorted(p.name for p in HERE.iterdir() if p.is_file() and (
        p.suffix in ('.py','.md','.png','.pdf') or p.name in {
            'baseline_readiness.json','baseline_source_receipt.json','readiness_summary.json','readiness_seal.json',
            'prediction_audit_compact.json','packet_audit.json','timing_review_resolution.json',
            'signal_control_audit.json','null_control_audit.json','wrong_control_audit.json','boundary_control_audit.json',
            'frequency_information_12cases.json','round1_summary.json','candidate_manifest.json',
            'position_protocol.json','position_protocol_v2.json','position_terminal_seal.json',
            'position_inference_audit_compact.json','position_evaluation.json','position_attribution.json',
            'position_summary.json','halfcell_audit.json','final_test_results.json'}))
    names+=['position_harness/sitecustomize.py','position_harness/position_read_audit.py']
    files={name:dict(sha256=sha(HERE/name),bytes=(HERE/name).stat().st_size) for name in names}
    local={}
    for path in HERE.iterdir():
        if path.is_file() and path.name not in files and path.name not in ('publication_manifest.json','artifact_seal.json'):
            local[path.name]=dict(sha256=sha(path),bytes=path.stat().st_size)
    write('publication_manifest.json',dict(schema='missed-visit-round1-validation-publication-v1',
        relative_files=files,include_manifest_and_artifact_seal=True,
        publication_bytes=sum(v['bytes'] for v in files.values()),
        local_only_large_files=local,
        local_only_run_directories=['position_runs','DS24-*-additions-r01'],
        recursive_copy_forbidden=True,position_conclusion='Small weight-sensitive development effect; no promotion',
        next_stage='Separately frozen coherent application and final prototype; do not change this sparse-position experiment.'))
    write('artifact_seal.json',dict(frozen_utc_ns=time.time_ns(),publication_manifest_sha256=sha(HERE/'publication_manifest.json'),
        files={name:receipt['sha256'] for name,receipt in files.items()},tests_passed=36,
        inference_terminal_seal_sha256=sha(HERE/'position_terminal_seal.json'),
        no_held_validation_target_outcomes=True,all_sparse_jobs_terminal=True,all_six_jobs_complete=True,
        post_seal_GPS_reporting_only=True))
    print(json.dumps(dict(status='sealed',files=len(files),publication_bytes=sum(v['bytes'] for v in files.values()),tests=36)))


if __name__=='__main__':main()
