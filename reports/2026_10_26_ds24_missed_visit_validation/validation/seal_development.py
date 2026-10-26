"""Lean independent development artifact seal; held target outcomes excluded."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
FILES=('PROTOCOL.md','PRE_FREEZE_FEEDBACK.md','ROOT_SCREEN_BINDING.md','CONTROL_FINDINGS.md','FINDINGS.md','STATUS.md',
    'audit_prediction.py','prediction_audit.json','audit_controls.py','control_audit.json','audit_recorded.py','recorded_audit.json',
    'candidate_manifest.json','graph_additions.py','graph_audit.json','report.py','summary.json','validation_summary.png','validation_summary.pdf',
    'test_reference_audit.py','test_control_receipt.py','test_staging.py','development_test_results.json','seal_development.py')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def main():
    graph=json.loads((HERE/'graph_audit.json').read_text());summary=json.loads((HERE/'summary.json').read_text())
    assert graph['new_curved']==summary['new_curved_graph']==6 and graph['new_graph']==7
    assert json.loads((HERE/'development_test_results.json').read_text())['all_passed']
    files={name:dict(sha256=sha(HERE/name),bytes=(HERE/name).stat().st_size) for name in FILES}
    manifest=dict(schema='independent-R02-development-publication/v1',files=files,total_bytes=sum(v['bytes'] for v in files.values()),
        scope='fixed12development cases only; original held target outcomes remain closed',
        new_native=9,new_in_graph=7,new_curved=6,high_channel_curved=3,high_channel_curved_nonzero_innovation=0,
        numerical_reruns=0,position_runs=0,geographic_truth_used=False)
    write(HERE/'development_publication_manifest.json',manifest)
    write(HERE/'development_artifact_seal.json',dict(manifest_sha256=sha(HERE/'development_publication_manifest.json'),files=len(files),
        total_bytes=manifest['total_bytes'],tests=4,all_passed=True,held_target_outcomes_opened=False,development_only=True))
    print(dict(files=len(files),bytes=manifest['total_bytes'],manifest_sha256=sha(HERE/'development_publication_manifest.json')))
if __name__=='__main__':main()
