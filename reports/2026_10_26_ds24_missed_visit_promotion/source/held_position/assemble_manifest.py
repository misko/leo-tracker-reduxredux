"""Seal every finite attempt before objective replay or geographic evaluation."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation')
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

def index_unique(rows):
    seen=set()
    for row in rows:
        key=row['case'],row['variant']
        if key in seen:raise ValueError('duplicate logical position job: '+str(key))
        seen.add(key)
    return seen

def main():
    base=read(HERE/'baseline_queue/protocol.json');candidate=read(HERE/'coherent_candidates/protocol.json')
    seals=[HERE/'terminal_seal.json',HERE/'baseline_v3/first_terminal_seal.json',HERE/'baseline_queue/terminal_seal.json',HERE/'coherent_candidates/terminal_seal.json',OLD/'position_terminal_seal.json',OLD/'coherent_application/position_final_terminal_seal.json']
    protected={};jobs=[]
    for path in seals:
        seal=read(path);assert seal['all_terminal']
        assert not seal.get('denied_paths',seal.get('denied_reads',[]))
        protected[str(path)]=sha(path)
        for p,h in seal.get('output_sha256',seal.get('terminal_output_hashes',{})).items():assert sha(p)==h,p
    for path in [HERE/'baseline_queue/protocol.json',HERE/'coherent_candidates/protocol.json']:
        protocol=read(path);protected[str(path)]=sha(path)
        for p,h in dict(protocol['sources_sha256'],**protocol['inputs_sha256']).items():assert sha(p)==h,p;protected[p]=h
    for seal_path in [HERE/'baseline_v3/first_terminal_seal.json',HERE/'baseline_queue/terminal_seal.json',HERE/'coherent_candidates/terminal_seal.json']:
        for r in read(seal_path)['results']:
            stratum='held' if r['case'] in base['strata']['held'] else 'development'
            jobs.append(dict(case=r['case'],variant=r['variant'],root=r['root'],status=r['status'],seconds=r['seconds'],stratum=stratum,reused_control=False))
    for c in read(HERE/'development_control_equality.json')['controls']:
        e=read(Path(c['root'])/'execution.json');assert e['status']=='complete'
        for p,h in c['terminal_output_hashes'].items():assert sha(p)==h,p
        jobs.append(dict(case=c['case'],variant='baseline',root=c['root'],status='complete',seconds=e['seconds'],stratum='development',reused_control=True))
    for c in read(HERE/'candidate_control_equality.json')['controls']:
        for p,h in c['terminal_output_hashes'].items():assert sha(p)==h,p
        jobs.append({k:c[k] for k in ('case','variant','root','status','seconds','stratum','reused_control')})
    keys=index_unique(jobs);aliases=candidate['comparison_aliases']
    assert len(jobs)==46 and len(aliases)==26
    assert len(keys|{(r['case'],r['variant']) for r in aliases})==72
    # Privileged metadata hashes are checked here; no native IQ is read.
    upstream=read(HERE/'upstream_binding_audit.json');assert upstream['all_passed']
    for p,h in upstream['bound_sha256'].items():assert sha(p)==h,p
    for p in [Path(__file__),HERE/'test_assemble_manifest.py',HERE/'development_control_equality.json',HERE/'candidate_control_equality.json',HERE/'upstream_binding_audit.json',HERE/'noise_input_audit.json',HERE/'audit_caps.py',HERE/'test_audit_caps.py',HERE/'cap_audit_final.json',HERE/'export_endpoints_v2.py',HERE/'test_export_endpoints_v2.py']:
        protected[str(p)]=sha(p)
    manifest=dict(schema='DS24-coherent-promotion-complete-inference-manifest/v1',all_attempts_terminal=True,coherent_handoff_sealed=True,terminal_seals=list(map(str,seals)),protected_hashes=protected,jobs=sorted(jobs,key=lambda r:(r['stratum'],r['case'],r['variant'])),comparison_aliases=aliases,strata=base['strata'],import_only_failed_sparse_attempts=36,fresh_baseline_attempts=22,fresh_candidate_attempts=18,reused_baseline_controls=2,reused_candidate_controls=4,logical_comparisons=72,upstream_metadata_audit_revalidated=True,no_GPS_evaluation_performed=True)
    write(HERE/'inference_manifest.json',manifest)
    print(dict(actual_endpoint_jobs=len(jobs),logical_jobs=72,caps=sum(r['status']=='capped' for r in jobs),manifest_sha256=sha(HERE/'inference_manifest.json')),flush=True)

if __name__=='__main__':main()
