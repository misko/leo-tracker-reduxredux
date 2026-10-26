"""Compact exact scientific capsule; large repeated parent ledgers stay bound."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    protocol=read(HERE/'protocol.json');compact=HERE/'compact';compact.mkdir(exist_ok=True)
    p=read(HERE/'preparation.json')
    records=[]
    for row in p['records']:
        ids=row['likelihood_membership'];inj=row['injection']
        records.append(dict(case=row['case'],arm=row['arm'],zero_delta_exact=row['zero_delta_exact'],
            zero_delta_errors=row['zero_delta_errors'],original_saved_objective_replay_difference=row['original_saved_objective_replay_difference'],
            likelihood_counts={k:ids[k] for k in ('curved_count','predictive_count','union_sha256')},
            selected_IDs_sha256=inj['native_IDs_sha256'],selected_ID_count=len(inj['native_IDs']),
            unchanged_inference_fingerprint=inj['unchanged_inference_fingerprint'],
            unchanged_noise_fingerprint=inj['unchanged_noise_fingerprint'],nonselected_graph_values_exact=inj['nonselected_graph_values_exact']))
    write(compact/'preparation_summary.json',dict(source_path=str(HERE/'preparation.json'),source_sha256=sha(HERE/'preparation.json'),
        all_passed=p['all_passed'],seconds=p['seconds'],test_stdout=p['test_stdout'],records=records))
    for case in protocol['cases']:
        for method in protocol['methods']:
            for arm in protocol['arms']:
                folder=HERE/case/method/arm
                raw=read(folder/'raw_endpoint.json');gate=read(folder/'gates.json');result=read(HERE/case/method/(arm+'_result.json'))
                ids=raw['likelihood_membership'];member=gate['membership'];s=raw['summary']
                write(compact/f'{case}_{method}_{arm}.json',dict(result=result,
                    original_raw_path=str(folder/'raw_endpoint.json'),original_raw_sha256=sha(folder/'raw_endpoint.json'),
                    original_gate_path=str(folder/'gates.json'),original_gate_sha256=sha(folder/'gates.json'),
                    full_objective=raw['full_objective'],curved_objective=s['curved_negative_twice_elbo'],predictive_objective=raw['predictive_objective'],
                    phase_reference=s['phase_reference'],state=s['state'],noise_precision=raw['noise_precision'],
                    coefficient=raw['coefficient'],coefficient_prior_precision=raw['coefficient_prior_precision'],
                    final_log_precision_change=raw['final_log_precision_change'],
                    original_single_arm_valid=gate['original_single_arm_valid'],Gamma_converged=gate['Gamma_converged'],
                    final_phase_change_s=gate['final_phase_change_s'],maximum_unclipped_phase_s=gate['maximum_unclipped_phase_s'],
                    original_accepted_IDs_lost=gate['original_accepted_IDs_lost'],baseline_reproduction=gate['baseline_reproduction'],
                    likelihood_counts={k:ids[k] for k in ('curved_count','predictive_count','union_sha256')},
                    total_GLRT=member['total_GLRT'],associated_IDs=member['associated'],associated_percent=member['percent'],
                    postfit_only_IDs=len(member['postfit_only_observation_ids']),
                    failed_curved_gates=[r for r in s['gates']['tracks'] if not r['compatible']],
                    failed_predictive_gates=[r for r in s['linear_gates'] if not r['compatible']],
                    raw_and_gate_details_external=True))
    readback=read(HERE/'postfit_readback/result.json');table=[]
    for row in readback['rows']:
        number=57955 if 'RX1-' in row['owner'] else 56094
        c=next(x for x in row['candidates'] if x['norad']==number)
        table.append(dict(arm=row['arm'],method=row['method'],owner=row['owner'],norad=number,
            chosen_norad=row['chosen_norad'],profile_RMS_hz=c['profile_RMS_hz'],bias_hz=c['bias_hz'],
            slope_z=c['noise']['slope_z'],slope_limit=3,failed_predicates=';'.join(c['failed_predicates']),
            other_predicates_pass=all(on for name,on in c['predicates'].items() if name!='noise_slope')))
    with (compact/'postfit_predicates.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    published=[];external=[]
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name=='lean_publication.json' or any(x in path.parts for x in ('__pycache__','.pytest_cache')):continue
        record=dict(path=str(path),relative_path=str(path.relative_to(HERE)),sha256=sha(path),bytes=path.stat().st_size)
        if path.name in ('raw_endpoint.json','gates.json','preparation.json','injection.json'):
            external.append(dict(record,status='original_full_detail_retained_locally_compact_exact_summary_published'))
        else:published.append(record)
    dependencies=dict(protocol['files'])
    for name in ('measurement/corrections.json','measurement/RF_seal.json','position_go.json'):
        path=ROOT/name;dependencies[str(path)]=sha(path)
    for name,digest in dependencies.items():
        path=Path(name)
        if path.is_relative_to(HERE):continue
        if sha(path)!=digest:raise ValueError('external binding changed: '+name)
        external.append(dict(path=name,sha256=digest,bytes=path.stat().st_size,status='external_original_input_or_other_published_branch'))
    write(HERE/'lean_publication.json',dict(schema='complete-owner-position-lean-publication/v1',published=published,external_files=external,
        published_bytes=sum(p['bytes'] for p in published),raw_recorded_IQ_copied=False,
        exact_completed_endpoint_count=8,all_compact_endpoint_and_qualification_data_published=True,
        replay_limitation='Full scientific replay requires declared original absolute source/parent/array paths. RF seals retain those hashes; compact endpoints, convergence/gates, coefficients, coverage and geography are included without the repeated full parent/residual ledgers.'))
    print(json.dumps(dict(files=len(published),bytes=sum(p['bytes'] for p in published),external=len(external),manifest_sha256=sha(HERE/'lean_publication.json'))))


if __name__=='__main__':main()
