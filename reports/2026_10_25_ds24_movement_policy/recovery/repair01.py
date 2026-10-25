"""Technical support-replay repair; preserve graph results and all r01 bytes."""

import argparse
import copy
import time
import traceback
from pathlib import Path

import numpy as np

import recovery as r
from ds23_active_mode_support import make_problem

OUT = r.HERE/'repair01'
ORIGINAL_BUILD = r.build
ORIGINAL_REFIT = r.support.refit


def corrected_build(d, arm, reference, kind='graph'):
    if kind != 'support':
        return ORIGINAL_BUILD(d, arm, reference, kind)
    p = make_problem(d['scan'], d['node'], d['keep'], arm, np.asarray(reference),
        d['powers'], d['means'], d['model'], set(d['original_protected']))
    r.attach_event_predictive(p, d['entries'], d['powers'])
    return r.cached(p)


def verify_original_seal():
    r.verify()
    seal = r.read(r.HERE/'scientific_seal.json')
    for name,digest in seal['files'].items():
        if r.sha(r.HERE/name) != digest:
            raise ValueError('original scientific result changed: '+name)


def freeze():
    verify_original_seal()
    before = r.read(r.HERE/'execution.json')
    budget = {c:dict(original_support_seconds=r.read(r.HERE/c/'support/result.json')['seconds'],
        remaining_support_seconds=240-r.read(r.HERE/c/'support/result.json')['seconds']) for c in r.CASES}
    protocol = dict(revision='recovery support technical repair01',
        reason='original fitter protected incumbent context; reporting mistakenly protected augmented context',
        scientific_model_candidates_gates_priors_budgets_unchanged=True,
        original_graph_fits_reused_without_refitting=True,
        original_execution_seconds=before['seconds'],
        original_start_utc_ns=r.read(r.HERE/'execution_start.json')['started_utc_ns'],
        original_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json'),
        original_protocol_sha256=r.sha(r.HERE/'protocol.json'),
        coordinator_decision_sha256=r.sha(r.HERE.parent/'recovery_repair_decision.json'),
        original_parent_protected={c:r.read(r.HERE/c/'parent.json')['original_protected'] for c in r.CASES},
        corrected_builder_uses_original_protected_context=True,
        raw_support_arm_checkpointed_before_replay=True,
        graph_refits=0, new_candidates=0, new_rescues=0,
        repeated_first_support_pair_reason='original pair not serialized before reporting exception; limitation retained',
        support_maximum_proposals=2, phase_rounds=5, position_steps=48,
        per_case_budget=budget, global_pilot_seconds=1800,
        global_budget_uses_original_wall_start=True,
        exact_original_candidate_order_sha256={c:r.sha(r.HERE/c/'support/candidate_order.json') for c in r.CASES},
        source_sha256={str(p):r.sha(p) for p in [Path(__file__), r.HERE/'test_repair01.py']},
        graph_result_sha256={c:r.sha(r.HERE/c/'graph/result.json') for c in r.CASES},
        no_GPS=True,no_receiver_model_change=True,no_native_path_or_IQ=True)
    r.write_new(OUT/'protocol.json',protocol)
    r.write_new(OUT/'protocol_seal.json',dict(protocol_sha256=r.sha(OUT/'protocol.json')))


def verify():
    verify_original_seal()
    protocol=r.read(OUT/'protocol.json')
    if r.read(OUT/'protocol_seal.json')['protocol_sha256'] != r.sha(OUT/'protocol.json'):
        raise ValueError('repair protocol seal changed')
    for name,digest in protocol['source_sha256'].items():
        if r.sha(name)!=digest:raise ValueError('repair source changed')
    return protocol


def run():
    protocol=verify()
    approval=r.read(r.HERE.parent/'audit/recovery_repair01_preflight.json')
    if approval.get('all_passed') is not True or approval['protocol_sha256']!=r.sha(OUT/'protocol.json'):
        raise ValueError('independent repair preflight required')
    if (OUT/'execution_start.json').exists():raise FileExistsError('repair cannot restart')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if r.os.environ.get(name)!='1':raise ValueError('single numerical thread required')
    contexts={case:r.context(case) for case in r.CASES}
    for case,d in contexts.items():
        if sorted(d['original_protected']) != protocol['original_parent_protected'][case]:
            raise ValueError('original parent protection changed')
    remaining_global=1800-(time.time_ns()-protocol['original_start_utc_ns'])/1e9
    deadline=time.monotonic()+remaining_global
    began=time.monotonic()
    r.write_new(OUT/'execution_start.json',dict(started_utc_ns=time.time_ns(),
        remaining_global_wall_seconds=remaining_global,
        protocol_sha256=r.sha(OUT/'protocol.json')))
    r.build=corrected_build
    rows=[]
    for case in r.CASES:
        start=time.monotonic();out=OUT/case;out.mkdir(exist_ok=False)
        d=contexts[case];parent=r.read(r.HERE/case/'parent.json')['coverage']
        graph=r.read(r.HERE/case/'graph/result.json')
        # Verify exact frozen order before spending a single repaired fit.
        expected=r.read(r.HERE/case/'support/candidate_order.json')['candidates']
        candidates=r.eligible_support(d,graph['trials'])
        regenerated=[dict(trial_index=t['trial_index'],additions=t['additions'],
            disabled_new_one_owner_orbit_families=disabled) for t,disabled in candidates]
        if regenerated!=expected:raise ValueError('repair changed candidate order')
        counter=[0]
        def checkpoint_refit(*args):
            fitted=ORIGINAL_REFIT(*args)
            r.write_new(out/f'raw_arm_{counter[0]:02d}.json',dict(arm=args[3],
                original_protected=sorted(d['original_protected']),endpoint=fitted,
                checkpoint_before_membership_replay=True))
            counter[0]+=1
            return fitted
        r.support.refit=checkpoint_refit
        try:
            r.alarm_until(min(deadline,start+protocol['per_case_budget'][case]['remaining_support_seconds']),
                'remaining original support/global budget exhausted')
            result=r.support_stage(d,parent,graph,out)
        except Exception as exc:
            traceback.print_exc()
            result=dict(status='timeout' if isinstance(exc,TimeoutError) else 'failed',
                error=repr(exc),traceback=traceback.format_exc(),selected=None,trials=[],
                policy_arms=d['arms'],baseline_fallback=True,raw_arms_preserved_separately=True)
        finally:r.signal.setitimer(r.signal.ITIMER_REAL,0)
        seconds=time.monotonic()-start
        result.update(case=case,stage='support_repair01',seconds=seconds,
            total_support_seconds_including_original=seconds+protocol['per_case_budget'][case]['original_support_seconds'],
            graph_refits=0,no_GPS=True,protocol_sha256=r.sha(OUT/'protocol.json'))
        r.write_new(out/'result.json',result)
        rows.append(dict(case=case,status=result['status'],selected=result['selected'] is not None,
            seconds=seconds,total_support_seconds=result['total_support_seconds_including_original'],raw_arms=counter[0]))
    total=time.monotonic()-began
    r.write_new(OUT/'execution.json',dict(rows=rows,seconds=total,
        scientific_active_seconds_including_original=protocol['original_execution_seconds']+total,
        wall_seconds_from_original_start=(time.time_ns()-protocol['original_start_utc_ns'])/1e9,
        all_terminal=True,graph_refits=0,no_GPS=True))
    r.write_new(OUT/'scientific_seal.json',dict(sealed_utc_ns=time.time_ns(),
        original_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json'),
        no_GPS_before_seal=True,files={str(p.relative_to(OUT)):r.sha(p) for p in sorted(OUT.rglob('*.json')) if p.name!='scientific_seal.json'}))
    print('support repair RF results sealed',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['freeze','verify','run'])
    args=parser.parse_args();globals()[args.stage]()


if __name__=='__main__':main()
