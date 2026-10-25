"""Bounded fixed-endpoint replay with independently constructed gate views."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'scientific'
sys.path.insert(0,str(SCI))
import adapter as a
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from probe_ds23_frequency_events import summary as legacy_summary
from algo02_scan import pair_passes


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def independent_view(p,x,conservative):
    c=p.calculate(x)
    nb,ns=p.hardware.shape[1],p.smooth.shape[1]
    first=nb+ns;stop=first+len(p.labels)+3*len(p.original_calibration_supported)
    frequency=c['intercept']+c['features'][:,first:stop]@c['coefficient'][first:stop]/p.q
    gate=dict(c)
    if p.extra_families:
        mean=c['features'][:,p.extra_start:]@c['coefficient'][p.extra_start:]
        if conservative:
            gate['conditional_residual_hz']=c['conditional_residual_hz']+mean
            if p.linear_entries:
                gate['linear_raw_prediction_residual_hz']=c['linear_raw_prediction_residual_hz']+c['predictive_features'][:,p.extra_start:]@c['coefficient'][p.extra_start:]
        else:frequency=frequency+mean/p.q
    view=SimpleNamespace(**vars(p))
    view.supported=list(p.original_calibration_supported) if conservative else sorted(set(p.original_calibration_supported)|set(p.extra_families))
    view.calculate=lambda _:gate
    view.conditional_frequency=lambda _:(frequency,c['elevation'])
    return view,gate


def coverage(view,x,entries,saved,d):
    extension=extend_associations(view,x,saved['gates'])
    lookup={t['key']:t for t in view.scan.tracks}
    explicit=[dict(e,compatible=q['compatible']) for e,q in zip(entries,saved['linear_gates'],strict=True)]
    keys={r['component'] for r in explicit};explicitids={oid for r in explicit for oid in r['observation_ids']}
    owned=[]
    for row in extension['tracks']:
        if not row['compatible'] or row['component'] in keys:continue
        ids=row.get('observation_ids',lookup[row['component']]['observation_ids'])
        if set(ids)&explicitids:continue
        owned+=ids
    owned += [oid for row in explicit if row['compatible'] for oid in row['observation_ids']]
    if len(owned)!=len(set(owned)):raise ValueError('accepted ID duplication in independent replay')
    curved=[oid for i,sl in zip(view.members,view.slices,strict=True) for oid,use in zip(view.scan.tracks[i]['observation_ids'],view.keep[sl],strict=True) if use]
    predictive=[oid for e in entries for oid in e['observation_ids']]
    native={row['observation_id'] for row in d['observations']}
    if not set(owned+curved+predictive)<=native:raise ValueError('non-native accepted or likelihood ID')
    return sorted(set(owned+curved+predictive)),sorted(owned),len(native)


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('150s independent endpoint replay cap')))
    signal.setitimer(signal.ITIMER_REAL,150.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=read(SCI/'protocol.json');execution=read(SCI/'fits_summary.json')
    check('protocol unchanged',sha(SCI/'protocol.json')==read(ROOT/'audit/preflight.json')['protocol_sha256'])
    for path,h in protocol['source_input_hashes'].items():check('source/input '+path,sha(path)==h)
    for name in ('fixed_seal.json','fits_seal.json'):
        for path,h in read(SCI/name)['files'].items():check(name+' '+path,sha(path)==h)
    check('exact four terminal denominators',execution['all_selected_terminal'] and [r['case'] for r in execution['cases']]==protocol['ordered_cases'])
    check('600s cumulative science',execution['cumulative_charged_seconds']<=600.)
    endpoint_replays=0;rows=[];case_outcomes=[]
    for case in execution['cases']:
        name=case['case'];d=a.r.context(name)
        check(name+' no runtime failure',case['status']=='complete' and not case['failures'])
        check(name+' within120s cumulative case cap',case['scientific_cumulative_case_seconds']<=120.)
        check(name+' operational reference unchanged',case['operational_policy_source']=='original_reference')
        valid={};memberships=[]
        for method in protocol['methods']:
            savedmethod=case['methods'][method];replayed={};literal={}
            for arm,saved in savedmethod['arms'].items():
                prefix=name+method+arm
                directory=SCI/'fits'/name/method/arm
                output=read(directory/'result.json');arrays=dict(np.load(output['arrays']['path']))
                x=np.asarray(saved['endpoint_east_north_km']);ref=np.asarray(saved['phase_reference'])
                p=a.build(d,arm,ref,method);c=p.calculate(x)
                check(prefix+' saved endpoint VI replay',abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])<1e-6)
                for field in ('coefficient','features','noise_precision','coefficient_prior_precision','conditional_residual_hz'):
                    check(prefix+' saved arrays '+field,np.allclose(c[field],arrays[field],rtol=0,atol=1e-7))
                view,gate=independent_view(p,x,True);fullview,_=independent_view(p,x,False)
                check(prefix+' conservative curved mean omission',np.allclose(gate['conditional_residual_hz'],arrays['conservative_conditional_residual_hz'],rtol=0,atol=1e-7))
                if d['entries']:check(prefix+' conservative predictive mean omission',np.allclose(gate['linear_raw_prediction_residual_hz'],arrays['conservative_predictive_residual_hz'],rtol=0,atol=1e-7))
                result=legacy_summary(view,x,d['entries']);expanded=legacy_summary(fullview,x,d['entries'])
                for key in ('gates','linear_gates'):
                    def decisions(summary):
                        rs=summary[key]['tracks'] if key=='gates' else summary[key]
                        return [(q['component'],q['compatible']) for q in rs]
                    check(prefix+' original conservative '+key,decisions(result)==decisions(saved))
                    check(prefix+' literal expanded '+key,decisions(expanded)==decisions(output['literal_expanded_fullmean']))
                accepted,raw,native=coverage(view,x,d['entries'],result,d)
                check(prefix+' exact postfit replay',accepted==output['coverage']['accepted_observation_ids'] and raw==output['coverage']['raw_gate_accepted_observation_ids'] and native==output['coverage']['total_GLRT'])
                members=output['likelihood_membership'];ids=members['curved_observation_ids']+members['predictive_observation_ids']
                check(prefix+' same unique likelihood',members==case['likelihood_membership'] and len(ids)==len(set(ids))==members['union_unique'])
                memberships.append(members)
                hist=saved['history'];history_reference=np.zeros(len(ref))
                for epoch in hist[:-1]:history_reference=np.clip(epoch['unclipped_absolute_phase_s'],-15,15)
                check(prefix+' original five-round reference',len(hist)==5 and np.array_equal(history_reference,ref))
                result.update(final_phase_change_s=saved['final_phase_change_s'],final_log_precision_change=c['final_log_precision_change'])
                expanded.update(final_phase_change_s=saved['final_phase_change_s'],final_log_precision_change=c['final_log_precision_change'])
                replayed[arm]=result;literal[arm]=expanded
                # Removing only the owner cascade identifies primitive failures;
                # this is an explanatory control, never an eligibility gate.
                primitive_view=SimpleNamespace(**vars(view));primitive_view.supported=[]
                primitive=retained_metrics(primitive_view,x)
                primitive_rows={q['component']:q for q in primitive['tracks']}
                failed=[q for q in result['gates']['tracks'] if not q['compatible']]
                primitive_fail=[q for q in failed if not primitive_rows[q['component']]['compatible']]
                owner_only=[q for q in failed if primitive_rows[q['component']]['compatible']]
                literal_primitive_view=SimpleNamespace(**vars(fullview));literal_primitive_view.supported=[]
                literal_primitive=retained_metrics(literal_primitive_view,x)
                lp={q['component']:q for q in literal_primitive['tracks']}
                literal_failed=[q for q in expanded['gates']['tracks'] if not q['compatible']]
                rows.append(dict(case=name,method=method,arm=arm,
                    conservative_failed_components=[q['component'] for q in failed],
                    primitive_failed_rows=primitive_fail,original_owner_cascade_only=owner_only,
                    predictive_failures=[q for q in result['linear_gates'] if not q['compatible']],
                    literal_failed_count=len(literal_failed),literal_owner_only_count=sum(lp[q['component']]['compatible'] for q in literal_failed),
                    phase_change_s=saved['final_phase_change_s'],maximum_unclipped_phase_s=float(np.max(abs(result['state']['phases']))),
                    Gamma_change=float(c['final_log_precision_change']),
                    lost_baseline_retained_IDs=sorted(set(case['coverage']['original_reference'][arm]['accepted_observation_ids'])-set(accepted))))
                endpoint_replays+=1
            RF=pair_passes(replayed,include_linear=True)
            phase=all(np.max(abs(q['state']['phases']))<=15.000001 and q['final_phase_change_s']<=.01 for q in replayed.values())
            precision=all(np.isfinite(q['final_log_precision_change']) and q['final_log_precision_change']<=1e-5 for q in replayed.values())
            valid[method]=bool(RF and phase and precision)
            check(name+method+' paired original conservative qualification',valid[method]==savedmethod['conservative_paired_valid'])
            check(name+method+' literal qualification',bool(pair_passes(literal,include_linear=True) and phase and precision)==savedmethod['literal_expanded_paired_valid'])
        preserved=all(set(case['coverage']['original_reference'][arm]['accepted_observation_ids'])<=set(case['coverage']['retained_uncertainty'][arm]['accepted_observation_ids']) for arm in ('c0','fitted_c'))
        adopted=bool(valid['retained_uncertainty'] and preserved and not case['failures'])
        check(name+' frozen research fallback',adopted==case['research_policy_adopted'] and preserved==case['candidate_all_baseline_accepted_IDs_preserved'])
        case_outcomes.append(dict(case=name,candidate_conservative_paired_valid=valid['retained_uncertainty'],all_baseline_retained_IDs_preserved=preserved,research_adopted=adopted,operational_policy_source='original_reference'))
    check('all16 endpoint attempts retained',endpoint_replays==16)
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,checks=checks,endpoint_replays=endpoint_replays,rows=rows,case_outcomes=case_outcomes,
        seconds=time.monotonic()-began,protocol_sha256=sha(SCI/'protocol.json'),fits_seal_sha256=sha(SCI/'fits_seal.json'),source_sha256=sha(__file__),
        position_optimization_calls=0,GPS_or_position_errors_read=False,
        gate_replay='independent conservative/fullmean views, original helpers and explicit owner-cascade separation',
        recommendation='all terminal RF bindings/controls/decisions pass audit; geographic evaluation may be released by coordinator; no operational adoption')
    (ROOT/'audit/terminal.json').write_text(json.dumps(output,default=a.r.encode,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('checks','rows')}))


if __name__=='__main__':main()
