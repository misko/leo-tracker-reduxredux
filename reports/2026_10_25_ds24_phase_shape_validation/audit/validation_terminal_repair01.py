"""Bounded actual RF endpoint replay after coordinator terminal signal.

No optimizer, geographic truth, distance function or evaluation result is used.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np

HERE=Path(__file__).resolve().parent
V=HERE.parent/'validation'
EXPECTED='ee529f8f5477b43527a1fd8f8537cf746eaf92ab3cb1fa0f96bb236c73a719f1'
CAP_SECONDS=180.
ARMS=('c0','fitted_c')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def write(path,value):
    def encode(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    with Path(path).open('x') as stream:json.dump(value,stream,default=encode,indent=2,allow_nan=False);stream.write('\n')


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def gate_map(summary):
    return dict(curved={row['component']:bool(row['compatible']) for row in summary['gates']['tracks']},
                predictive={row['component']:bool(row['compatible']) for row in summary.get('linear_gates',[])})


def endpoint_in_box(summary):
    x=np.asarray(summary['endpoint_east_north_km'])
    return bool(x.shape==(2,) and np.isfinite(x).all() and np.max(abs(x))<=12.50000001)


def canonical_phase_change(saved):
    """Audit-only schema adapter; never mutate the scientific saved record."""
    result=dict(saved)
    history=saved.get('history')
    declared=saved.get('final_phase_change_s')
    if 'final_phase_change_s' not in saved:
        if not isinstance(history,list) or len(history)!=5 or [h.get('epoch') for h in history]!=list(range(5)):
            raise ValueError('legacy summary requires exact five-epoch phase history')
        if any('phase_change_s' not in h or not np.isfinite(float(h['phase_change_s'])) or float(h['phase_change_s'])<0 for h in history):
            raise ValueError('invalid legacy phase history')
        declared=history[-1]['phase_change_s']
    value=float(declared)
    if not np.isfinite(value) or value<0:raise ValueError('invalid final phase change')
    if history and 'phase_change_s' in history[-1]:
        last=float(history[-1]['phase_change_s'])
        if not np.isfinite(last) or abs(last-value)>1e-12:raise ValueError('conflicting declared/history phase change')
    result['final_phase_change_s']=value
    return result


def likelihood(d,p):
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
            for oid,use in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if use]
    predictive=[oid for e in d['entries'] for oid in e.get('observation_ids',d['scan'].tracks[e['track_index']]['observation_ids'])]
    available={row['observation_id'] for row in d['observations']}
    valid=bool(len(curved)==len(set(curved)) and len(predictive)==len(set(predictive)) and
               not set(curved)&set(predictive) and (set(curved)|set(predictive))<=available)
    return dict(curved_unique=len(curved),predictive_unique=len(predictive),union_unique=len(curved)+len(predictive),
                total_GLRT=len(available),union_ids_sha256=hashlib.sha256(json.dumps(sorted(set(curved)|set(predictive))).encode()).hexdigest()),valid


def main():
    began=time.monotonic();timeout=False
    frozen=read(HERE/'validation_terminal_repair01_freeze.json')
    for path,expected in frozen['files'].items():
        if sha(path)!=expected:raise ValueError('terminal audit source changed after freeze: '+path)
    prior=read(HERE/'validation_terminal_audit.json');priorseal=read(V/'RF_seal.json')
    spent=float(priorseal['audit_seconds']);remaining=CAP_SECONDS-spent
    if remaining<=0:raise TimeoutError('original180s audit budget exhausted')
    # Carry successful replays only after exact source/output hash verification.
    for path,expected in priorseal['files'].items():
        if sha(path)!=expected:raise ValueError('initial replay binding changed: '+path)
    if prior['endpoint_replays']!=42 or any(not c['passed'] for c in prior['checks']):
        raise ValueError('unexpected prior audit; no broad repair authorized')
    cases_to_replay=['RX1V-0001']
    if any(prior['per_case'][c]['errors'] for c in prior['per_case'] if c not in cases_to_replay):
        raise ValueError('prior completed case had an unaudited error')
    checks=list(prior['checks']);case_results={c:v for c,v in prior['per_case'].items() if c not in cases_to_replay}
    endpoint_count=prior['endpoint_replays']
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s separate RF audit cap')))
    signal.setitimer(signal.ITIMER_REAL,remaining-(time.monotonic()-began))
    def check(test,passed,**data):checks.append(dict(test=test,passed=bool(passed),**data))
    protocol=read(V/'protocol.json');cases=protocol['cases']
    execution=read(V/'execution.json');manifest=read(V/'sample.json')
    check('exact frozen protocol',sha(V/'protocol.json')==EXPECTED)
    check('terminal exact8 denominator',execution['all_terminal'] and len(execution['rows'])==len(cases)==8 and
          len({r['case'] for r in execution['rows']})==8 and {r['case'] for r in execution['rows']}==set(cases))
    terminal={r['case']:r for r in execution['rows']}
    selected={r['dataset_label']:r for r in manifest['selected']}
    bindings_valid=True
    for binding in protocol['bindings']:
        ok=sha(binding['path'])==binding['sha256'];bindings_valid &= ok
        check('frozen source/input binding',ok,path=binding['path'])
    sys.path.insert(0,'/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/evaluation')
    runner=load(V/'runner.py','terminal_frozen_runner')
    from matched_controls import measurement_binding,factor_contract,phase_pair_valid
    from probe_ds23_graph_seeded_paths import build,coverage
    from probe_ds23_frequency_events import summary
    adapter=load(runner.OLD/'receiver/adapter.py','terminal_frozen_rx1')
    replay_ok=True;files={}
    try:
        # Hash scientific outputs before propagation, under the same hard cap.
        # The coordinator permits this only after all producer processes finish.
        for path in sorted(V.rglob('*')):
            if path.is_file() and path.name!='RF_seal.json':files[str(path)]=sha(path)
        for case in cases_to_replay:
            info=dict(baseline_available=False,baseline_paired_valid=False,comparison_available=False,
                      terminal_status=terminal[case]['status'],policy_source='baseline',methods={},errors=[])
            case_results[case]=info
            try:
                check('per-case terminal receipt',read(V/case/'execution.json')==terminal[case],case=case)
                input_receipt_path=V/case/'input_receipt.json'
                if input_receipt_path.exists():
                    input_receipt=read(input_receipt_path)
                    input_ok=(input_receipt['recording_id']==selected[case]['recording_id'] and
                              input_receipt['sample_sha256']==sha(V/'sample.json') and
                              input_receipt['raw_authority_digest']==selected[case]['raw_authority_digest'])
                    if input_receipt['status']=='exported':input_ok &= sha(V/case/'tracking.json')==input_receipt['tracking_sha256']
                    check('export source identity/hash',input_ok,case=case);bindings_valid &= input_ok
                prep_path=V/case/'preparation_receipt.json'
                if prep_path.exists():
                    for relative,expected in read(prep_path)['files_sha256'].items():
                        ok=sha(V/relative)==expected;bindings_valid &= ok
                        check('prepared scientific input hash',ok,case=case,path=relative)
                basepath=V/'family_cavity/position'/(case+'.json')
                if not basepath.exists() or read(basepath).get('status')!='complete':
                    info['baseline_unavailable_reason']='fresh reference absent or incomplete; selected case retained'
                    continue
                d=runner.baseline_context(case);before=measurement_binding(d)
                cutoff=d['scan'].receipt['cutoff_utc_ns']
                causal=all(max(e['provenance']['element_epoch_utc_ns'],e['provenance']['collected_utc_ns'])<=cutoff
                           for e in d['scan'].elements.values())
                check('entire inference catalogue causal',causal,case=case,count=len(d['scan'].elements));bindings_valid &= causal
                comparison_path=V/case/'comparison.json'
                comparison=read(comparison_path) if comparison_path.exists() else None
                if comparison is not None:
                    check('comparison protocol/reference unchanged',comparison['protocol_sha256']==EXPECTED and
                          comparison['baseline']==d['arms'] and comparison['baseline_sha256']==sha(basepath),case=case)
                    info['comparison_available']=comparison.get('status')=='complete'
                changed=adapter.expand(d,'fast_rx1_rf50')
                data_by_method={'baseline':d,'matched_cold_baseline':d,'rx1_rf50':changed}
                baseline_contracts={};baseline_membership=None;rebuilt_pairs={};covariances={}
                for method,data in data_by_method.items():
                    pair={};method_details={}
                    for arm in ARMS:
                        if method=='baseline':saved=canonical_phase_change(d['arms'][arm])
                        else:
                            path=V/case/(method+'_'+arm+'.json')
                            if not path.exists():continue
                            saved=canonical_phase_change(read(path))
                        p=build(data,'default',arm,saved['phase_reference'])
                        contract=factor_contract(p,d['entries'])
                        member,unique=likelihood(d,p)
                        check('physical unique native likelihood ownership',unique,case=case,method=method,arm=arm)
                        if method=='baseline':
                            baseline_contracts[arm]=contract
                            if baseline_membership is None:baseline_membership=member
                        check('same likelihood ownership across all models/arms',member==baseline_membership,case=case,method=method,arm=arm)
                        check('physical factors preserved',contract==baseline_contracts[arm],case=case,method=method,arm=arm)
                        if not endpoint_in_box(saved):
                            # The original rejection predicate already fails;
                            # do not propagate outside the allowed region.
                            actual=dict(saved)
                            detail=dict(endpoint_in_bounds=False,original_single_arm_valid=False,
                                        replay_kind='original endpoint bound predicate; invalid endpoint not propagated')
                        else:
                            actual=summary(p,np.asarray(saved['endpoint_east_north_km']),d['entries'])
                            actual['final_phase_change_s']=saved['final_phase_change_s']
                            error=float(actual['negative_twice_elbo']-saved['negative_twice_elbo'])
                            tolerance=min(1e-3,1e-8*max(abs(saved['negative_twice_elbo']),1.))
                            same_gates=gate_map(actual)==gate_map(saved)
                            check('actual saved endpoint objective replay',abs(error)<=tolerance,case=case,method=method,arm=arm,error=error,tolerance=tolerance)
                            check('actual original curved/predictive gates replay',same_gates,case=case,method=method,arm=arm)
                            covariances.setdefault(method,{})[arm]=coverage(data,'default',arm,saved)
                            detail=dict(endpoint_in_bounds=True,objective_replay_difference=error,gate_decisions_replay=same_gates,
                                original_single_arm_valid=bool(phase_pair_valid({a:actual for a in ARMS})),
                                maximum_unclipped_phase_s=float(np.max(abs(np.asarray(actual['state']['phases'])))),
                                final_phase_change_s=actual['final_phase_change_s'],
                                precision_change_diagnostic=float(p.calculate(np.asarray(saved['endpoint_east_north_km']))['final_log_precision_change']),
                                gate_counts={kind:dict(total=len(values),failed=sum(not b for b in values.values())) for kind,values in gate_map(actual).items()},
                                replay_kind='actual unchanged saved endpoint, original summary and coverage; no optimization')
                            endpoint_count += 1
                        pair[arm]=actual;method_details[arm]=detail
                    rebuilt_pairs[method]=pair
                    paired=bool(set(pair)==set(ARMS) and phase_pair_valid(pair))
                    info['methods'][method]=dict(arms=method_details,paired_valid=paired,complete_pair=set(pair)==set(ARMS))
                    if method=='baseline':
                        info.update(baseline_available=set(pair)==set(ARMS),baseline_paired_valid=paired,
                                    likelihood_membership=baseline_membership)
                check('baseline input not mutated',measurement_binding(d)==before,case=case)
                if comparison is not None and info['comparison_available']:
                    for method in ('matched_cold_baseline','rx1_rf50'):
                        check('saved paired qualification replay',info['methods'][method]['paired_valid']==comparison['results'][method]['paired_valid'],case=case,method=method)
                    adopted=info['methods']['rx1_rf50']['paired_valid']
                    check('original paired adoption/fallback replay',comparison['adopted']==adopted and
                          comparison['policy_source']==('rx1_rf50' if adopted else 'baseline'),case=case)
                    check('comparison native likelihood counts',comparison['likelihood_membership']==baseline_membership,case=case)
                    info['policy_source']=comparison['policy_source']
                    for method,arms in covariances.items():
                        for arm,current in arms.items():
                            recorded=comparison['coverage'][method][arm]
                            check('actual unique postfit coverage replay',set(current['accepted_observation_ids'])==set(recorded['accepted_observation_ids']) and
                                  current['associated']==recorded['associated']==len(set(current['accepted_observation_ids'])) and
                                  current['total_GLRT']==recorded['total_GLRT'],case=case,method=method,arm=arm)
                    for arm in ARMS:
                        lost=sorted(set(covariances['baseline'][arm]['accepted_observation_ids'])-set(covariances['rx1_rf50'][arm]['accepted_observation_ids']))
                        check('postfit loss report exact, not new gate',lost==comparison['lost_baseline_postfit_IDs'][arm],case=case,arm=arm)
                else:
                    info['fallback_reason']='comparison absent/incomplete; partial fits remain diagnostic and are not adopted'
                info['usable_baseline']=bool(info['baseline_available'] and info['baseline_paired_valid'])
            except TimeoutError:
                raise
            except Exception as exc:
                replay_ok=False;info['errors'].append(dict(error=repr(exc),traceback=traceback.format_exc()))
    except TimeoutError as exc:
        timeout=True;replay_ok=False;check('RF audit within180s',False,error=repr(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    # No further geometry after timeout; unreviewed cases remain explicitly
    # unavailable and the global prerequisite fails shut.
    for case in cases:
        case_results.setdefault(case,dict(baseline_available=False,baseline_paired_valid=False,comparison_available=False,
            terminal_status=terminal[case]['status'],errors=[dict(error='audit cap before case review')]))
    source_immutable=sha(V/'protocol.json')==EXPECTED and all(sha(b['path'])==b['sha256'] for b in protocol['bindings'])
    check('source/protocol immutable through audit',source_immutable)
    all_passed=all(c['passed'] for c in checks) and replay_ok and not timeout
    audit=dict(all_passed=all_passed,checks=checks,per_case=case_results,endpoint_replays=endpoint_count,
               carried_endpoint_replays=42,new_endpoint_replays=endpoint_count-42,
               prior_audit_seconds=spent,cumulative_audit_seconds=spent+time.monotonic()-began,
               prior_audit_sha256=sha(HERE/'validation_terminal_audit.json'),prior_failed_seal_sha256=sha(V/'RF_seal.json'),
               repair='audit-local final phase field from exact frozen five-epoch history; no saved output, scientific fit or gate changed',
               protocol_sha256=EXPECTED,seconds=time.monotonic()-began,audit_cap_seconds=CAP_SECONDS,
               optimization_calls=0,geographic_truth_or_errors_used=False,audit_source_sha256=sha(Path(__file__)))
    audit_path=HERE/'validation_terminal_repair01_audit.json';write(audit_path,audit)
    # Bind all complete and partial artifacts, including unqualified outcomes.
    # Hashing is streaming; no endpoint is selected by its geographic position.
    files[str(audit_path)]=sha(audit_path);files[str(Path(__file__))]=sha(Path(__file__))
    files[str(V/'RF_seal.json')]=sha(V/'RF_seal.json')
    seal=dict(all_selected_terminal=bool(execution['all_terminal'] and set(terminal)==set(cases)),
              protocol_immutable=source_immutable,original_gates_replayed=all_passed,
              bindings_audited=bool(bindings_valid and source_immutable),protocol_sha256=EXPECTED,
              files=files,per_case=case_results,endpoint_replays=endpoint_count,
              audit_seconds=spent+time.monotonic()-began,repair_audit_seconds=time.monotonic()-began,audit_cap_seconds=CAP_SECONDS,
              audit_passed=all_passed,optimization_calls=0,geographic_truth_or_errors_used=False)
    if seal['audit_seconds']>CAP_SECONDS:
        seal.update(original_gates_replayed=False,audit_passed=False,audit_cap_reached=True)
    write(V/'RF_seal02.json',seal)
    print(json.dumps(dict(all_passed=all_passed,endpoint_replays=endpoint_count,seconds=seal['audit_seconds'],
        cases={case:{key:info[key] for key in ('baseline_available','baseline_paired_valid','comparison_available')} for case,info in case_results.items()}),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--coordinator-terminal-go',action='store_true',required=True)
    parser.parse_args();main()
