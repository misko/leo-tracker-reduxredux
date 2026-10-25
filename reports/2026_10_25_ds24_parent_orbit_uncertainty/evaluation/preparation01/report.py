"""Evaluate only sealed saved endpoints after explicit coordinator release."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from metrics import ARMS, SITE, TIE_KM, distance, local_latlon, operational_policy, research_eligible, research_policy, summarize

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
CASES = tuple(f'DS24-{i:04d}' for i in range(10,14))
VARIANTS = ('original_reference','matched_cold_baseline','raw_candidate','research_policy','operational_reference')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def freeze():
    names=('metrics.py','test_metrics.py','report.py','test_report.py')
    write(HERE/'evaluator_freeze.json',dict(files={str(HERE/n):sha(HERE/n) for n in names},
        cases=CASES,arms=ARMS,variants=VARIANTS,evaluation_only_site_latlon=SITE,earth_radius_km=6371.,
        tie_km=TIE_KM,operational_policy='original_reference always',
        research_policy='paired conservative gates + phase/Gamma convergence + complete original accepted-ID preservation in both arms',
        unavailable='null error, retained original selected denominator; no replacement',
        geography_selects_no_endpoint_or_gate=True))


def authorize(root=STUDY):
    evaluation=root/'evaluation';frozen=read(evaluation/'evaluator_freeze.json')
    for path,h in frozen['files'].items():
        if sha(path)!=h:raise ValueError('evaluator source changed after freeze')
    if frozen['cases']!=list(CASES) or frozen['evaluation_only_site_latlon']!=list(SITE):
        raise ValueError('evaluation panel/site changed')
    go=read(evaluation/'coordinator_release.json')
    seal_path=root/'scientific/RF_seal.json'
    if go.get('approved') is not True or go['RF_seal_sha256']!=sha(seal_path):
        raise ValueError('matching coordinator RF release required')
    if go['evaluator_freeze_sha256']!=sha(evaluation/'evaluator_freeze.json'):
        raise ValueError('coordinator release does not bind evaluator freeze')
    audit_path=Path(go['terminal_audit_path'])
    if sha(audit_path)!=go['terminal_audit_sha256'] or read(audit_path).get('all_passed') is not True:
        raise ValueError('independent terminal audit required')
    seal=read(seal_path);bound={}
    for path,h in seal['files'].items():
        p=Path(path)
        if not p.is_absolute():p=seal_path.parent/p
        p=p.resolve();h=h.removeprefix('sha256:')
        if sha(p)!=h:raise ValueError('RF-sealed artifact changed: '+str(p))
        bound[str(p)]=h
    required=[root/'scientific/fits'/case/'result.json' for case in CASES]
    if any(str(p.resolve()) not in bound for p in required):
        raise ValueError('all four case results must be RF-sealed')
    return dict(freeze=frozen,release=go,RF_seal_sha256=sha(seal_path),bound=bound)


def accepted(coverage):
    ids=coverage['accepted_observation_ids']
    if len(ids)!=len(set(ids)) or coverage['associated']!=len(ids):
        raise ValueError('complete accepted-ID ledger/count mismatch')
    if not 0<=len(ids)<=coverage['total_GLRT']:raise ValueError('invalid native GLRT denominator')
    return set(ids)


def failed_gate_count(record):
    if record is None or 'gates' not in record:return None
    gates=record.get('gates',{}).get('tracks',[])+record.get('linear_gates',[])
    return sum(not g['compatible'] for g in gates)


def rows_from_case(case,result):
    reference=result['original_reference_arms'];methods=result['methods'];coverage=result['coverage']
    candidate=methods['retained_uncertainty'];cold=methods['matched_cold_baseline']
    if result['operational_policy_source']!='original_reference':
        raise ValueError('operational policy changed from frozen reference')
    oldids={a:accepted(coverage['original_reference'][a]) for a in ARMS}
    newids={a:accepted(coverage['retained_uncertainty'][a]) if a in coverage.get('retained_uncertainty',{}) else None for a in ARMS}
    preserved=all(newids[a] is not None and oldids[a]<=newids[a] for a in ARMS)
    if result['candidate_all_baseline_accepted_IDs_preserved']!=preserved:
        raise ValueError('saved complete accepted-ID conjunction differs')
    eligible=research_eligible(candidate['conservative_paired_valid'],
        candidate['phase_Gamma_converged_both_arms'],preserved)
    if result['adopted']!=eligible:raise ValueError('saved research policy differs from frozen conjunction')
    research,source=research_policy(reference,candidate['arms'],eligible)
    operational,_=operational_policy(reference)
    if operational is not reference:raise ValueError('operational reference not exact')
    output=[]
    for arm in ARMS:
        records=dict(original_reference=reference[arm],matched_cold_baseline=cold['arms'].get(arm),
            raw_candidate=candidate['arms'].get(arm),research_policy=research[arm],operational_reference=operational[arm])
        literal=candidate.get('literal_expanded_fullmean_arms',{}).get(arm)
        for variant in VARIANTS:
            record=records[variant]
            method=('retained_uncertainty' if variant=='raw_candidate' or variant=='research_policy' and eligible else
                    'matched_cold_baseline' if variant=='matched_cold_baseline' else 'original_reference')
            cov=coverage.get(method,{}).get(arm)
            ids=accepted(cov) if cov is not None else None
            position=record.get('endpoint_east_north_km') if record else None
            latlon=local_latlon(position) if position is not None else None
            if record and record.get('endpoint_latlon') is not None and latlon is not None:
                if max(abs(a-b) for a,b in zip(latlon,record['endpoint_latlon'],strict=True))>1e-9:
                    raise ValueError('saved endpoint coordinate conversion differs')
            lost=sorted(oldids[arm]-ids) if ids is not None else None
            if method=='retained_uncertainty' and record and 'endpoint_east_north_km' in record and 'likelihood_conditional_RMS_hz' not in record:
                raise ValueError('candidate fullmean RMS must remain distinct from conservative gate RMS')
            row=dict(case=case,arm=arm,variant=variant,available=latlon is not None,
                east_km=position[0] if position is not None else None,north_km=position[1] if position is not None else None,
                latitude=latlon[0] if latlon is not None else None,longitude=latlon[1] if latlon is not None else None,
                error_km=distance(latlon) if latlon is not None else None,
                research_pair_eligible=eligible,research_policy_source=source,operational_policy_source='original_reference',
                conservative_pair_valid=(candidate['conservative_paired_valid'] if method=='retained_uncertainty' else
                    cold['conservative_paired_valid'] if method=='matched_cold_baseline' else None),
                phase_Gamma_pair_converged=(candidate['phase_Gamma_converged_both_arms'] if method=='retained_uncertainty' else
                    cold['phase_Gamma_converged_both_arms'] if method=='matched_cold_baseline' else None),
                negative_twice_elbo=record.get('negative_twice_elbo') if record else None,
                conservative_gate_RMS_hz=record.get('RMS_hz') if record else None,
                likelihood_fullmean_RMS_hz=record.get('likelihood_conditional_RMS_hz',record.get('RMS_hz')) if record else None,
                failed_conservative_gate_rows=failed_gate_count(record),
                candidate_literal_expanded_pair_valid=candidate['literal_expanded_paired_valid'],
                candidate_failed_literal_gate_rows=failed_gate_count(literal),
                accepted_union_count=len(ids) if ids is not None else None,
                raw_gate_accepted_count=len(cov['raw_gate_accepted_observation_ids']) if cov and 'raw_gate_accepted_observation_ids' in cov else None,
                total_GLRT=cov['total_GLRT'] if cov else None,lost_baseline_accepted_count=len(lost) if lost is not None else None,
                lost_baseline_accepted_IDs=lost,source_method=method)
            output.append(row)
    return output


def run():
    authorization=authorize();rows=[];case_metadata=[]
    for case in CASES:
        path=STUDY/'scientific/fits'/case/'result.json';result=read(path)
        rows+=rows_from_case(case,result)
        case_metadata.append(dict(case=case,source_path=str(path),source_sha256=sha(path),
            research_adopted=result['adopted'],saved_research_policy_source=result['research_policy_source'],
            operational_policy_source=result['operational_policy_source'],
            likelihood_membership=result['likelihood_membership'],failures=result.get('failures',{})))
    if len(rows)!=len(CASES)*len(ARMS)*len(VARIANTS):raise ValueError('evaluation denominator changed')
    for row in rows:
        baseline=next(q for q in rows if q['case']==row['case'] and q['arm']==row['arm'] and q['variant']=='original_reference')
        for field,target in [('error_km','error_change_km'),('negative_twice_elbo','objective_change'),
                             ('conservative_gate_RMS_hz','gate_RMS_change_hz'),('likelihood_fullmean_RMS_hz','fullmean_RMS_change_hz')]:
            row[target]=row[field]-baseline[field] if row[field] is not None and baseline[field] is not None else None
    statistics=[]
    for arm in ARMS:
        baseline=[next(q for q in rows if q['case']==c and q['arm']==arm and q['variant']=='original_reference')['error_km'] for c in CASES]
        for variant in VARIANTS:
            errors=[next(q for q in rows if q['case']==c and q['arm']==arm and q['variant']==variant)['error_km'] for c in CASES]
            stats=summarize(errors,baseline)
            if variant=='operational_reference' and errors!=baseline:raise ValueError('operational geographic output changed')
            statistics.append(dict(arm=arm,variant=variant,**stats))
    output=HERE/'report';output.mkdir(exist_ok=False)
    write(output/'positions.json',dict(rows=rows))
    with (output/'positions.csv').open('x',newline='') as stream:
        fields=[k for k in rows[0] if k!='lost_baseline_accepted_IDs'];writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
        writer.writeheader();writer.writerows({k:r[k] for k in fields} for r in rows)
    write(output/'summary.json',dict(statistics=statistics,cases=case_metadata,
        operational_policy='original_reference for every case',research_policy='hypothetical conservative paired qualification and complete accepted-ID preservation; no promotion',
        selected_cases=CASES,evaluation_only_site_latlon=SITE,RF_seal_sha256=authorization['RF_seal_sha256'],
        evaluator_freeze_sha256=sha(HERE/'evaluator_freeze.json'),new_fits=0,no_geographic_selection=True))
    write(output/'data_seal.json',dict(files={str(p):sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        RF_seal_sha256=authorization['RF_seal_sha256'],evaluator_freeze_sha256=sha(HERE/'evaluator_freeze.json')))
    print(json.dumps(statistics,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=('freeze','run'),required=True)
    args=parser.parse_args();globals()[args.stage]()
