"""Artifact-only terminal replay of support bounds and decision semantics."""
import hashlib
import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.special import logsumexp
from scipy.stats import t

HERE=Path(__file__).resolve().parent
SCI=HERE.parent/'scientific'
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/nomination')


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def array_sha(value): return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
def close(a,b,tol=1e-8):
    return a is None and b is None or a is not None and b is not None and abs(a-b)<=tol


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='terminal.json')
    args=parser.parse_args();output=HERE/args.output
    if output.exists(): raise FileExistsError('preserve terminal audit')
    began=time.monotonic();checks=[];counts=dict(arm_rows=0,candidate_rows=0,
        certified_orders=0,absolute_orderings=0,precise_candidates=0,known_zero=0,
        null_guard_failed=0,failed_candidates=0)
    def check(name,passed,**detail):checks.append(dict(name=name,passed=bool(passed),**detail))
    protocol_hash=sha(SCI/'protocol.json');protocol=read(SCI/'protocol.json')
    preflight=read(HERE/'preflight.json');rf=read(SCI/'RF_seal.json');execution=read(SCI/'execution.json')
    bindings={str(SCI/'RF_seal.json'):sha(SCI/'RF_seal.json'),str(SCI/'execution.json'):sha(SCI/'execution.json'),
        str(SCI/'protocol.json'):protocol_hash,str(HERE/'preflight.json'):sha(HERE/'preflight.json'),
        str(HERE.parent/'coordinator_go.json'):sha(HERE.parent/'coordinator_go.json')}
    bad=[path for path,digest in rf['files'].items() if sha(path)!=digest]
    bad_inputs=[path for path,digest in protocol['source_input_hashes'].items() if sha(path)!=digest]
    check('frozen protocol, approval and all RF/source/input hashes',not bad and not bad_inputs and
        preflight['all_passed'] and preflight['protocol_sha256']==protocol_hash==rf['protocol_sha256']==execution['protocol_sha256'] and
        read(HERE.parent/'coordinator_go.json')['approved'] is True,
        bad_RF_paths=bad,bad_input_paths=bad_inputs)
    old=read(OLD/'RF_seal.json')
    check('old immutable scientific outputs',all(sha(p)==h for p,h in old['files'].items()))
    totals=protocol['preparation_scientific_seconds']+sum(row['scientific_worker_seconds'] for row in execution['cases'])
    check('frozen cumulative budget, no fits or regenerated observations',
        close(totals,execution['total_scientific_seconds']) and totals<=600.01 and
        execution['position_fits']==0 and not execution['observations_regenerated'] and not execution['parent_relearned'],
        summed_scientific_worker_seconds=totals,wall_seconds=execution['wall_seconds'])
    trial_slots={(row['case'],q['trial']) for row in execution['cases'] for q in row['trials']}
    check('all12 selected trial terminal slots retained',trial_slots=={(c,i) for c in ('DS24-0010','DS24-0011') for i in range(6)})
    details=[]
    for case in ('DS24-0010','DS24-0011'):
        context=read(OLD/case/'context.json')
        with np.load(OLD/case/'context.npz') as catalog:
            phase_means=catalog['phase_means_s'].copy();phase_sds=catalog['phase_sd_s'].copy()
        for trial in range(6):
            screen=read(OLD/case/f'trial{trial}'/'screen.json')
            for arm in ('c0','fitted_c'):
                path=SCI/case/f'trial{trial}'/(arm+'_result.json')
                if not path.exists():
                    details.append(dict(case=case,trial=trial,arm=arm,result_available=False))
                    continue
                record=read(path);counts['arm_rows']+=1
                original=OLD/case/f'trial{trial}'
                with np.load(original/'observations.npz') as obs:
                    expected_hashes=dict(original_values_sha256=array_sha(obs['values_hz']),
                                         native_ids_sha256=array_sha(obs['native_ids']))
                with np.load(original/(arm+'_conditional.npz')) as saved:
                    for name,key in [('raw_hz','original_raw_sha256'),('covariance_hz2','original_covariance_sha256'),
                                     ('parent_coefficients','original_parent_coefficient_sha256'),
                                     ('parent_noise','original_parent_noise_sha256')]:
                        expected_hashes[key]=array_sha(saved[name])
                check('exact archived observation and arm-specific conditional arrays',
                      record['saved_input_hashes']==expected_hashes,case=case,trial=trial,arm=arm)
                check('exact ordinary candidate set/order',
                    [q['norad'] for q in record['candidates']]==screen['candidate_norads'] and
                    [q['candidate_index'] for q in record['candidates']]==screen['candidate_indices'],
                    case=case,trial=trial,arm=arm)
                old_result=read(OLD/case/f'trial{trial}'/(arm+'_result.json'))
                null=record['null'];delta=abs(null['objective']-null['independent_dense_objective'])
                expected_null=delta<=1e-7
                counts['null_guard_failed']+=not expected_null
                check('original normalized null and strict independent guard',
                    close(null['objective'],old_result['null']['objective']) and
                    close(delta,null['independent_dense_error']) and
                    null['independent_dense_passed']==expected_null,
                    case=case,trial=trial,arm=arm,null_error=delta)
                models=[(None,-.5*(null['objective']+1e-6),-.5*(null['objective']-1e-6))]
                valid_bounds=True;precision={};required=set(record['required_reference_norads'])
                for row in record['candidates']:
                    counts['candidate_rows']+=1;norad=row['norad']
                    old_row=next(q for q in old_result['candidates'] if q['norad']==norad)
                    if row['status']=='failed':
                        counts['failed_candidates']+=1;valid_bounds=False;precision[norad]=False;continue
                    support=read(SCI/case/f'support_{norad}.json')
                    empty=bool(support['certified'] and not support['inner_visible_intervals'] and not support['root_brackets'])
                    check('zero support distinguished from failure and unchanged old outcome retained',
                        (row['status']=='zero_physical_evidence')==empty and row['empty_support_certified']==empty and
                        row['old_status']==old_row['status'] and row['old_numerically_qualified']==old_row['numerically_qualified'],
                        case=case,trial=trial,arm=arm,norad=norad)
                    if empty:
                        counts['known_zero']+=1;models.append((norad,-np.inf,-np.inf));precision[norad]=True;continue
                    inner=row['physical_enclosure'];roots=row['root_enclosure']
                    lo=inner.get('lower_log_integral');hi=inner.get('upper_log_integral')
                    if roots.get('upper_log_integral') is not None:
                        hi=float(np.logaddexp(hi,roots['upper_log_integral'])) if hi is not None else roots['upper_log_integral']
                    check('full evidence upper bound includes root brackets',
                        close(lo,row['full_support_lower_log_integral']) and close(hi,row['full_support_upper_log_integral']),
                        case=case,trial=trial,arm=arm,norad=norad)
                    bound_ok=bool(support['certified'] and lo is not None and hi is not None and np.isfinite([lo,hi]).all() and lo<=hi)
                    valid_bounds &= bound_ok
                    if bound_ok:models.append((norad,lo,hi))
                    objective=row['objective']
                    error=max(abs(objective+2*lo),abs(objective+2*hi)) if objective is not None and lo is not None and hi is not None else None
                    base=bool(support['certified'] and error is not None and error<=1e-3 and
                        row['primary']['success'] and row['bracket_quadrature']['success'])
                    if norad in required and 'independent_reference' in row:
                        reference=row['independent_reference'];br=row['independent_bracket_reference']
                        difference=abs(objective-reference['objective']) if objective is not None and reference['objective'] is not None else 0.
                        base &= bool(reference['success'] and br['success'] and difference<=1e-3)
                        check('required independent scalar comparison',close(difference,row['primary_reference_error']),case=case,trial=trial,arm=arm,norad=norad)
                    precision[norad]=base;counts['precise_candidates']+=base
                    check('absolute score precision uses both full-enclosure endpoints',
                        row['numerically_qualified']==base and close(error,row['objective_distance_to_full_enclosure']),
                        case=case,trial=trial,arm=arm,norad=norad)
                    distribution=t(3,loc=row['original_phase_location_s'],scale=row['original_phase_sd_s']/np.sqrt(3))
                    j=row['candidate_index']
                    check('candidate-specific causal phase parameters remain exact archived inputs',
                        close(row['original_phase_location_s'],phase_means[j],1e-12) and
                        close(row['original_phase_sd_s'],phase_sds[j],1e-12),
                        case=case,trial=trial,arm=arm,norad=norad)
                    mass=distribution.cdf(15)-distribution.cdf(-15)
                    inner_mass=sum(distribution.cdf(b)-distribution.cdf(a) for a,b in support['inner_visible_intervals'])/mass
                    root_mass=sum(distribution.cdf(b)-distribution.cdf(a) for a,b in support['root_brackets'])/mass
                    changed=support['inner_visible_intervals']!=[[-15.,15.]] or bool(support['root_brackets'])
                    check('original prior normalization, support mass and changed-law classification',
                        close(mass,row['original_domain_prior_probability'],1e-12) and
                        close(inner_mass,row['inner_visible_prior_mass'],1e-12) and close(root_mass,row['root_bracket_prior_mass'],1e-12) and
                        row['support_law_changed']==changed and row['visible_mass_renormalized'] is False,
                        case=case,trial=trial,arm=arm,norad=norad)
                proved=False;winner=None;margin=None
                if expected_null and valid_bounds and len(models)==9:
                    for index,(identity,lower,_) in enumerate(models):
                        largest=max(q[2] for i,q in enumerate(models) if i!=index)
                        if lower>largest:proved=True;winner=identity;margin=lower-largest;break
                certificate=record['evidence_order_certificate']
                check('independent strict nine-model evidence-order proof',certificate['proved']==proved and
                    (not proved or certificate['winner_norad']==winner and certificate['absolute_score_precision_implied'] is False and
                     certificate['operational_identity_assignment'] is False),case=case,trial=trial,arm=arm)
                counts['certified_orders']+=proved
                finite=sorted([q for q in record['candidates'] if q.get('objective') is not None],key=lambda q:(q['objective'],q['norad']))
                expected_required={q['norad'] for q in finite[:2]}
                expected_required|={q['norad'] for q in sorted(
                    [v for v in old_result['candidates'] if v['status']=='complete'],
                    key=lambda q:(q['reference_objective'],q['norad']))[:2]}
                best_upper=min((-2*q['full_support_lower_log_integral'] for q in record['candidates']
                    if q.get('full_support_lower_log_integral') is not None),default=np.inf)
                for q in record['candidates']:
                    if q['status']=='zero_physical_evidence':continue
                    lo=q.get('full_support_upper_log_integral');hi=q.get('full_support_lower_log_integral')
                    if lo is None or hi is None:expected_required.add(q['norad']);continue
                    if -2*lo<=best_upper or -2*lo<=null['objective']<=-2*hi:
                        expected_required.add(q['norad'])
                check('old/new top-two and all ordering-sensitive independent references retained',
                      required==expected_required,case=case,trial=trial,arm=arm)
                exact=bool(expected_null and finite and precision.get(finite[0]['norad'],False) and
                    all(precision.get(j,False) for j in required) and
                    all(q['status'] in ('complete','zero_physical_evidence') for q in record['candidates']))
                check('absolute full-order precision remains separate',record['ordering_numerically_qualified']==exact,
                      case=case,trial=trial,arm=arm)
                counts['absolute_orderings']+=exact
                details.append(dict(case=case,trial=trial,arm=arm,result_available=True,strict_null_guard=expected_null,
                    absolute_precision_qualified=exact,ordering_certified=proved,winner_norad=winner,
                    minimum_log_evidence_margin=float(margin) if margin is not None and np.isfinite(margin) else None))
    checkpoints=sorted(SCI.glob('DS24-*/trial*/*_checkpoint.json'))
    check('checkpoint attempts preserved inside immutable RF capsule',
        all(str(p) in rf['files'] for p in checkpoints))
    counts['saved_candidate_checkpoints']=len(checkpoints)
    counts['partial_only_checkpoints']=len(checkpoints)-counts['candidate_rows']
    counts['missing_arm_results']=24-counts['arm_rows']
    if args.output!='terminal.json':
        bindings[str(HERE/'terminal.json')]=sha(HERE/'terminal.json')
        bindings[str(HERE/'terminal01.py')]=sha(HERE/'terminal01.py')
        check('original failed audit and exact source retained',
            read(HERE/'terminal.json')['source_sha256']==sha(HERE/'terminal01.py'))
        report=SCI/'report_support.py'
        check('exact original RF reporting bytes restored without exemption',
            sha(report)==rf['files'][str(report)])
    elapsed=time.monotonic()-began
    check('bounded independent audit',elapsed+preflight['cumulative_audit_seconds']<=180)
    check('all RF bytes unchanged during artifact audit',all(sha(p)==h for p,h in rf['files'].items()))
    receipt=dict(all_passed=all(q['passed'] for q in checks),protocol_sha256=protocol_hash,
        source_sha256=sha(__file__),bound_files=bindings,checks=checks,counts=counts,arm_outcomes=details,
        audit_wall_seconds=elapsed,cumulative_audit_seconds=elapsed+preflight['cumulative_audit_seconds'],
        propagation_calls=0,position_fits=0,new_integration_calls=0,geographic_truth_read=False)
    output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=receipt['all_passed'],counts=counts,
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'],
        failed=[q for q in checks if not q['passed']][:10])))


if __name__=='__main__':main()
