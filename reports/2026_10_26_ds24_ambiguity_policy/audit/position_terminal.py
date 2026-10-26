"""Artifact-only RF terminal audit; no position truth or orbital evaluations."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT=Path(__file__).resolve().parent.parent
SCI=ROOT/'position'
sys.path.insert(0,str(SCI))
import policy as e
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start=time.monotonic();checks=[];lost_details=[];completed=[]
    def check(name,passed,**detail):checks.append(dict(name=name,passed=bool(passed),**detail))
    protocol=read(SCI/'protocol.json');seal=read(SCI/'RF_seal.json');run=read(SCI/'execution.json')
    check('scientific source/input and terminal RF seals exact',
        sha(SCI/'protocol.json')==seal['protocol_sha256']=='60a2933eb2497d6f6b0b739f6fc22afe81070167649f5417a7845a1ee66963a0' and
        all(sha(p)==h for p,h in protocol['source_input_hashes'].items()) and all(sha(p)==h for p,h in seal['files'].items()))
    source_parent=read(e.r.SOURCE/'family_cavity/position/DS24-0011.json')
    saved=source_parent['policy_arms'];original=read(Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership/DS24-0011/parent.json'))['coverage']
    meta=read(e.OLD/'prepared/DS24-0011/metadata.json');target_ids=meta['entry']['observation_ids']
    check('all six declared method/arm outcomes retained with exact operational baseline fallback',
        len(run['all6_slots'])==6 and {(r['arm'],r['method']) for r in run['all6_slots']}=={(a,m) for a in e.ARMS for m in e.METHODS} and
        all(r['operational_policy']=='original_reference' for r in run['all6_slots']))
    for arm in e.ARMS:
        replay=read(SCI/arm/'initial_replay.json')
        check(arm+': all old probe/order scores reproduce before any fits',
            replay['passed'] and len(replay['rows'])==6 and
            all(r['maximum_error']<=1e-3 and max(abs(v-r['old_objective']) for v in r['order_objectives'].values())<=1e-3 for r in replay['rows']) and
            replay['old_interval'][0]<=replay['delta_secant']<=replay['old_interval'][1])
        for method in e.METHODS:
            row=read(SCI/arm/(method+'_result.json'));folder=SCI/arm/method
            if row['status']!='complete':
                check(arm+'/'+method+': method timeout preserves epoch0 only, no final endpoint or qualification',
                    method=='mixture' and row['status']=='failed_or_budget_limited' and
                    'TimeoutError' in row['error'] and not row['raw_endpoint_available'] and
                    (folder/'epoch0.json').exists() and not (folder/'raw_endpoint.json').exists() and
                    not (folder/'numerical_qualification.json').exists() and not (folder/'gates.json').exists())
                continue
            raw=read(folder/'raw_endpoint.json');gates=read(folder/'gates.json');num=read(folder/'numerical_qualification.json')
            hist=raw['history'];summary=gates['parent_summary'];member=gates['membership']
            check(arm+'/'+method+': original five refreshes, common cold start and actual raw endpoint checkpoint',
                len(hist)==5 and [r['epoch'] for r in hist]==list(range(5)) and
                np.array_equal(hist[0]['reference'],np.zeros(len(hist[0]['reference']))) and
                all(np.array_equal(hist[i]['reference'],np.clip(hist[i-1]['unclipped_posterior_phase'],-15,15)) for i in range(1,5)) and
                np.array_equal(raw['parent_phase_reference'],hist[-1]['reference']) and
                raw['scientific_fit_seconds']<=60.1 and raw['operational_policy']=='original_reference' and
                not raw['target_association_qualified'])
            check(arm+'/'+method+': exact original parent predicates and unclipped phase/Gamma flags',
                gates['parent_original_valid']==bool(e.r.valid({a:summary for a in e.ARMS})) and
                abs(gates['maximum_unclipped_phase_s']-np.max(abs(np.asarray(summary['state']['phases']))))<1e-12 and
                gates['Gamma_converged']==bool(np.isfinite(gates['final_log_precision_change']) and gates['final_log_precision_change']<=1e-5) and
                gates['final_phase_change_s']==hist[-1]['phase_change_s'] and row['parent_valid']==gates['parent_original_valid'])
            curved=set(member['curved_observation_ids']);predictive=set(member['predictive_observation_ids'])
            old=original[arm];lost=sorted(set(old['accepted_observation_ids'])-set(member['accepted_observation_ids']))
            check(arm+'/'+method+': all old curved/predictive likelihood IDs exact, postfit losses independently recomputed',
                curved==set(old['curved_observation_ids']) and predictive==set(old['predictive_observation_ids']) and
                not curved&predictive and not set(target_ids)&(curved|predictive) and
                lost==gates['original_accepted_IDs_lost'] and row['full_original_IDs_preserved']==(not lost))
            for association in old['associations']:
                removed=set(association['observation_ids'])&set(lost)
                if removed:lost_details.append(dict(arm=arm,method=method,norad=association.get('norad'),component=association['component'],points=len(removed),postfit_only=removed<=set(old['postfit_only_observation_ids'])))
            source=gates['source'];sg=source['original_target_gate']
            check(arm+'/'+method+': source rejection/support unchanged; factor inclusion never creates an owner',
                source['offered_native_IDs']==target_ids and sg['observation_ids']==target_ids and
                source['original_target_active_points']==0 and not source['original_growth_supported'] and
                not source['accepted_target'] and not gates['source_association_qualified'] and
                not sg['compatible'] and not sg['conditional_residual_gate']['compatible'])
            if method=='no_addition':
                expected=e.control_reproduction(raw['endpoint_east_north_km'],raw['parent_negative_twice_elbo'],saved[arm],
                    gates['original_reference_reproduction']['saved_same_reference_objective_difference'])
                check(arm+': no-addition exact endpoint/full parent objective reproduce saved reference',
                    expected==gates['original_reference_reproduction'] and expected['passed'] and
                    num['passed'] and num['target_factor_absent'])
            else:
                rows=num['rows'];gradients={str(n):np.array([(rows[1][str(n)]-rows[2][str(n)])/.02,
                    (rows[3][str(n)]-rows[4][str(n)])/.02]) for n in [16,32,64]}
                error=max(abs(r['16']-r['64']) for r in rows);ref=max(abs(r['32']-r['64']) for r in rows)
                grad=max(np.max(abs(gradients['16']-gradients['64'])),np.max(abs(gradients['32']-gradients['64'])))
                check(arm+': hard endpoint score/gradient comparisons independently replay from saved values',
                    len(rows)==5 and abs(error-num['maximum_score_error'])<1e-12 and abs(ref-num['reference_error'])<1e-12 and
                    abs(grad-num['maximum_gradient_error'])<1e-12 and num['passed']==bool(error<=1e-3 and ref<=1e-3 and grad<=1e-3) and
                    raw['target_prediction']['candidates'][0]['norad']==58175 and len(raw['target_prediction']['candidates'])==1)
            completed.append(dict(arm=arm,method=method,numerically_stable=num['passed'],parent_valid=gates['parent_original_valid'],
                old_likelihood_IDs_preserved=True,postfit_only_IDs_lost=len(lost),source_qualified=False))
    counts=Counter(r['status'] for r in run['all6_slots'])
    check('all terminal, no retries/budget transfer/new0012 work and cumulative600s cap',
        counts==Counter(complete=4,failed_or_budget_limited=2) and run['all_selected_terminal'] and
        abs(run['cumulative_scientific_seconds']-protocol['preparation_seconds']-sum(r['seconds'] for r in run['arms']))<1e-8 and
        run['cumulative_scientific_seconds']<=600 and not run['GPS_used'] and run['operational_policy']=='original_reference')
    result=dict(all_passed=all(r['passed'] for r in checks),checks=checks,seconds=time.monotonic()-start,
        protocol_sha256=sha(SCI/'protocol.json'),RF_seal_sha256=sha(SCI/'RF_seal.json'),source_sha256=sha(__file__),
        statuses=dict(counts),completed=completed,lost_postfit_details=lost_details,all_six_slots_terminal=True,
        RF_ready_for_separate_geographic_evaluation=True,mixture_final_endpoint_available=False,
        operational_policy='exact original saved reference for every method',new_position_fits=0,orbit_propagation_calls=0,
        geographic_truth_read=False,scope='Audit passing does not qualify target identity or endorse incomplete mixture positions.')
    result['RF_ready_for_separate_geographic_evaluation']=result['all_passed']
    with (ROOT/'audit/position_terminal.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'],checks=len(checks),seconds=result['seconds'],lost=lost_details,
        failed=[r for r in checks if not r['passed']])))


if __name__=='__main__':main()
