"""Lean final publication allowlist; raw/failed attempts stay locally preserved."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha
FILES=('FINDINGS.md','STATUS.md','POSITION_EXECUTION_PROPOSAL.md','EXECUTION_INFRASTRUCTURE_FAILURE.md',
    'audit_metadata.py','metadata_audit_v2.json','integrate.py','graph.py','plot_blocks.py','block_figure_manifest.json',
    'recorded_audit.json','candidate_manifest.json','baseline_equality_audit.json','position.py','position_protocol.json',
    'position_run_authorization.json','pre_execution_test_results.json','environment_identity_receipt.json',
    'ROOT_CONTINUATION_APPROVAL.json','resume_engine.py','engine_continuation_protocol.json','engine_continuation_authorization.json',
    'position_terminal_seal.json','position_final_terminal_seal.json','position_inference_audit_compact.json',
    'evaluate_position.py','position_evaluation_native.json','attribute_changes.py','position_association_changes.json',
    'execution_timing.json','report.py','summary.json','position_summary.png','position_summary.pdf',
    'test_metadata_diff.py','test_integration.py','test_reporting.py','final_test_results.json','seal.py')


def main():
    assert read(HERE/'final_test_results.json')['all_passed']
    assert read(HERE/'position_inference_audit.json')['all_complete']
    paths=[HERE/n for n in FILES]+sorted((HERE/'figures').glob('*'))
    paths += [HERE/'graphs'/case/'graph_audit.json' for case in ('DS24-0011','DS24-0097')]
    files={str(p.relative_to(HERE)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in paths}
    large={str(p):sha(p) for case in ('DS24-0011','DS24-0097') for p in [HERE/(case+'_additions.json'),HERE/'graphs'/case/'observations.json',HERE/'graphs'/case/'tracks.json',HERE/'graphs'/case/'radio_noise.json']}
    large.update({str(HERE/name):sha(HERE/name) for name in ('position_inference_audit.json','position_evaluation.json')})
    write(HERE/'publication_manifest.json',dict(schema='coherent-R01-application-independent-publication/v1',files=files,
        total_bytes=sum(v['bytes'] for v in files.values()),locally_preserved_large_artifacts=large,
        native_added=51,new_in_graph=46,new_curved_graph=32,new_curved_likelihood=13,new_predictive_likelihood=11,new_satellite_families=0,
        all_terminal=True,tests=12,held_localization_claim=False,uncertainty_calibrated=False,ALGO_promotion=False,
        first_attempt_and_infrastructure_continuation_separate=True,no_fresh_ALGO02_reruns=True))
    write(HERE/'artifact_seal.json',dict(manifest_sha256=sha(HERE/'publication_manifest.json'),files=len(files),
        total_bytes=sum(v['bytes'] for v in files.values()),tests=12,all_passed=True,
        immutable_sparse_R01_publication_unchanged=True,held_graph_reports_to_be_sealed_separately=True))
    print(dict(files=len(files),bytes=sum(v['bytes'] for v in files.values()),manifest_sha256=sha(HERE/'publication_manifest.json'),seal_sha256=sha(HERE/'artifact_seal.json')))


if __name__=='__main__':main()
