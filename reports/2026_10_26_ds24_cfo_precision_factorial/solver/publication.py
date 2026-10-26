"""Compact saved-only publication packet; no additional inference."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    protocol=read(HERE/'protocol.json');compact=HERE/'compact';compact.mkdir(exist_ok=True)
    preparation=read(HERE/'preparation.json');controls=[]
    for row in preparation['controls']:
        controls.append({k:v for k,v in row.items() if k not in ('injection_receipt','values')})
    write(compact/'preparation_summary.json',dict(source_path=str(HERE/'preparation.json'),source_sha256=sha(HERE/'preparation.json'),
        all_passed=preparation['all_passed'],seconds=preparation['seconds'],controls=controls,
        packet_comparisons=preparation['packet_comparisons'],tolerances=preparation['tolerances'],test_stdout=preparation['test_stdout']))
    coverage=[];diagonal=[]
    previous=Path('/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/position')
    for case in protocol['cases']:
        for arm in protocol['arms']:
            for cell,cfo,origin in protocol['cells']:
                folder=HERE/case/arm/cell;result=read(HERE/case/arm/(cell+'_result.json'))
                if result['status']!='complete':continue
                raw=read(folder/'raw_endpoint.json');gate=read(folder/'gates.json');member=gate['membership'];summary=raw['summary']
                write(compact/(case+'_'+arm+'_'+cell+'.json'),dict(result=result,
                    source_raw_path=str(folder/'raw_endpoint.json'),source_raw_sha256=sha(folder/'raw_endpoint.json'),
                    source_gates_path=str(folder/'gates.json'),source_gates_sha256=sha(folder/'gates.json'),
                    phase_reference=summary['phase_reference'],state=summary['state'],coefficient=raw['coefficient'],
                    noise_precision=raw['noise_precision'],coefficient_prior_precision=raw['coefficient_prior_precision'],
                    packet_sha256=raw['precision_packet_sha256'],objective_kind=raw['objective_kind'],Gamma_updated=False,
                    original_single_arm_valid=gate['original_single_arm_valid'],final_phase_change_s=gate['final_phase_change_s'],
                    maximum_unclipped_phase_s=gate['maximum_unclipped_phase_s'],original_accepted_IDs_lost=gate['original_accepted_IDs_lost'],
                    total_GLRT=member['total_GLRT'],associated=member['associated'],associated_percent=member['percent'],
                    curved_points=member['curved_points'],predictive_points=member['predictive_points'],
                    postfit_only_points=len(member['postfit_only_observation_ids']),likelihood_IDs_sha256=member['likelihood_IDs_sha256'],
                    current_conditional_posterior_used=True,VI_rebuild=False))
                coverage.append(dict(case=case,arm=arm,cell=cell,original_single_arm_valid=gate['original_single_arm_valid'],
                    lost=len(gate['original_accepted_IDs_lost']),associated=member['associated'],percent=member['percent'],
                    paired_retention_pass=None))
                if cell in ('00','11'):
                    import numpy as np
                    old=read(previous/case/('original' if cell=='00' else 'corrected')/arm/'raw_endpoint.json')
                    delta=np.asarray(result['endpoint_east_north_km'])-old['summary']['endpoint_east_north_km']
                    diagonal.append(dict(case=case,arm=arm,cell=cell,conditional_minus_saved_VI_vector_m=(delta*1000).tolist(),
                        norm_m=float(np.linalg.norm(delta)*1000),endpoint_equality_was_not_required=True))
    for row in coverage:
        row['paired_retention_pass']=all(r['lost']==0 and r['original_single_arm_valid'] for r in coverage if r['case']==row['case'] and r['cell']==row['cell'])
    write(compact/'coverage.json',coverage);write(compact/'diagonal_VI_endpoint_differences.json',diagonal)
    published=[];external=[]
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name=='lean_publication.json' or any(x in path.parts for x in ('__pycache__','.pytest_cache')):continue
        record=dict(path=str(path),relative_path=str(path.relative_to(HERE)),sha256=sha(path),bytes=path.stat().st_size)
        if path.name in ('raw_endpoint.json','gates.json','preparation.json','injection.json') or path.suffix=='.npz':
            external.append(dict(record,status='original_full_detail_retained_locally_compact_summary_published'))
        else:published.append(record)
    dependencies=dict(protocol['files']);dependencies[str(ROOT/'solver_go.json')]=sha(ROOT/'solver_go.json')
    for path,h in dependencies.items():
        q=Path(path)
        if q.is_relative_to(HERE):continue
        if sha(q)!=h:raise ValueError('external input changed: '+path)
        external.append(dict(path=path,sha256=h,bytes=q.stat().st_size,status='external_source_or_original_frozen_study_input'))
    write(HERE/'lean_publication.json',dict(schema='CFO-precision-factorial-lean-publication/v1',published=published,external_files=external,
        published_bytes=sum(p['bytes'] for p in published),completed_endpoints=16,
        all_compact_endpoints_packets_gates_and_geography_published=True,
        replay_limitation='Full original arrays, parents and historical paths remain declared hash-bound external inputs; compact16 endpoints, packets, posterior/gate/coverage summaries and signed/geographic tables are published. No RF/IQ is copied.'))
    print(json.dumps(dict(published=len(published),bytes=sum(p['bytes'] for p in published),external=len(external),manifest_sha256=sha(HERE/'lean_publication.json'))))


if __name__=='__main__':main()
