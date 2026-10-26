"""Seal R02 development only; coherent application/held stages stay separate."""
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def main():
    if not read(HERE/'verification.json')['all_passed']:raise ValueError('development verification failed')
    names=['PROTOCOL.md','FINDINGS.md','scorer.py','reader.py','study.py','test_scorer.py','summarize_controls.py',
        'summarize_recorded.py','verify.py','package.py','protocol.json','test_results.json','run_authorization.json',
        'control_summary.json','control_trials.csv','recorded_summary.json','recorded_cells.csv','candidate_manifest.json',
        'verification.json','fullwindow_primary_timing.png','fullwindow_primary_timing.pdf',
        'frequency_innovation_and_grid_origin.png','frequency_innovation_and_grid_origin.pdf']
    names+=['publication_allowlist.json','artifact_seal.json','publication_manifest.json']
    write(HERE/'publication_allowlist.json',dict(schema='round2-development-publication/v2',files=sorted(names),
        excluded_separate_stages=['expansion','expansion_v2','held_validation','live STATUS.md'],
        full_compressed_outcomes_and_checkpoints_local_only=True,raw_IQ_included=False))
    local=[HERE/n for n in names if n not in ['artifact_seal.json','publication_manifest.json']]
    local+=sorted((HERE/'outcomes').glob('*.gz'));local+=sorted((HERE/'checkpoints').glob('*.gz'))
    write(HERE/'artifact_seal.json',dict(schema='round2-development-artifact-seal/v2',sealed_utc_ns=time.time_ns(),
        files={str(f.relative_to(HERE)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in sorted(local)},
        scope='Primary full-window development only; coherent application and held stages sealed separately',
        requested_cells=576,all_cells_retained=True,stage='READY_FOR_COHERENCE_REVIEW',position_ready=False,
        no_independent_added_Doppler_points=True,no_raw_IQ=True))
    pub=[HERE/n for n in sorted(names) if n!='publication_manifest.json']
    write(HERE/'publication_manifest.json',dict(schema='round2-development-publication-manifest/v2',
        files={f.name:dict(sha256=sha(f),bytes=f.stat().st_size) for f in pub},
        total_bytes=sum(f.stat().st_size for f in pub),artifact_seal_sha256=sha(HERE/'artifact_seal.json'),
        raw_IQ_included=False,full_local_outcomes_retained=True))
    print('R02 development sealed',sha(HERE/'artifact_seal.json'),'publication_bytes',sum(f.stat().st_size for f in pub),flush=True)


if __name__=='__main__':main()
