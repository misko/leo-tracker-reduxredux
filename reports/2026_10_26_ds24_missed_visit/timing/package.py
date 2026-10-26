"""Final local seal and lean publication manifest; no outcome recomputation."""
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
    verification=read(HERE/'verification.json')
    if not verification['all_passed']:raise ValueError('verification failed')
    names=sorted(p.name for p in HERE.iterdir() if p.is_file() and p.suffix in ['.py','.md','.json','.csv','.png','.pdf'])
    names=sorted(set(names+['publication_allowlist.json','artifact_seal.json','publication_manifest.json']))
    write(HERE/'publication_allowlist.json',dict(schema='timing-lean-publication/v1',files=names,
        omitted_full_local_directories=['outcomes','selections','checkpoints','__pycache__'],
        all_trial_cell_denominators_included=True,all_raw_IQ_omitted=True,
        full_compressed_outputs_bound_by='artifact_seal.json'))
    local=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts
        and p.name not in ['artifact_seal.json','publication_manifest.json'])
    write(HERE/'artifact_seal.json',dict(schema='timing-local-artifact-seal/v1',sealed_utc_ns=time.time_ns(),
        files={str(p.relative_to(HERE)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in local},
        stage='READY_FOR_COHERENCE_REVIEW',position_ready=False,independent_added_Doppler_points=0,
        raw_IQ_included=False,source_protocol_sha256=sha(HERE/'protocol.json')))
    publication=[HERE/name for name in names if name!='publication_manifest.json']
    write(HERE/'publication_manifest.json',dict(schema='timing-publication-manifest/v1',
        files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in publication},
        total_bytes=sum(p.stat().st_size for p in publication),artifact_seal_sha256=sha(HERE/'artifact_seal.json'),
        no_raw_IQ=True,all_full_local_outcomes_retained=True))
    print('artifact_seal',sha(HERE/'artifact_seal.json'),'publication_bytes',sum(p.stat().st_size for p in publication),flush=True)


if __name__=='__main__':main()
