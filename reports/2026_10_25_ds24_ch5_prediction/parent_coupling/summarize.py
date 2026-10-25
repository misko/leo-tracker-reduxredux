"""Apply predeclared triage to sealed fixed-probe scores; no new RF evaluation."""
import json
from pathlib import Path
import hashlib

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    protocol=read(HERE/'protocol.json');result=read(HERE/'results.json');seal=read(HERE/'RF_seal.json')
    for path,digest in seal['files'].items():
        if sha(path)!=digest:raise ValueError('RF seal changed: '+path)
    summaries=[]
    for selected in protocol['selections']:
        case=selected['case'];arms=[]
        for arm in protocol['arms']:
            rows={row['offset_km']:row for row in result['rows'] if row['case']==case and row['arm']==arm}
            if set(rows)!=set(protocol['offsets_km']):
                arms.append(dict(arm=arm,status='unavailable',qualified=False));continue
            def delta(row,rule):
                def score(branch):
                    return (row['adaptive_reference'][branch]['objective'] if rule=='adaptive'
                            else row['records'][branch][rule]['objective'])
                return score('dynamic')-score('frozen')
            gradients={rule:{str(h):(delta(rows[h],rule)-delta(rows[-h],rule))/(2*h)
                              for h in (.05,.025)} for rule in ('161','321','adaptive')}
            score_error=max(abs(row['records'][branch]['321']['objective']-other)
                for row in rows.values() for branch in ('frozen','dynamic')
                for other in (row['records'][branch]['161']['objective'],row['adaptive_reference'][branch]['objective']))
            gradient_error=max(abs(gradients['321'][str(h)]-gradients[other][str(h)])
                               for h in (.05,.025) for other in ('161','adaptive'))
            finite_step=abs(gradients['321']['0.05']-gradients['321']['0.025'])
            adaptive_error=max(row['adaptive_reference'][branch]['relative_error'] for row in rows.values() for branch in ('frozen','dynamic'))
            dense_error=max(row['maximum_dense_node_error'] for row in rows.values())
            gradient=gradients['321']['0.025']
            step_tolerance=max(protocol['finite_step_gradient_tolerance_absolute_per_km'],
                               protocol['finite_step_gradient_tolerance_relative']*abs(gradient))
            qualified=(score_error<=protocol['score_tolerance'] and gradient_error<=protocol['gradient_tolerance_per_km']
                       and adaptive_error<=1e-6 and dense_error<=1e-5 and finite_step<=step_tolerance)
            uncertainty=max(gradient_error,finite_step/3,1e-8)
            shift=-gradient/(2*selected['weak_precision_per_km2'])
            error=uncertainty/(2*selected['weak_precision_per_km2'])
            material=(qualified and abs(shift)>=protocol['material_displacement_km']
                      and abs(shift)>protocol['material_to_numeric_error_ratio']*error)
            arms.append(dict(arm=arm,status='complete',qualified=qualified,gradients=gradients,
                central_delta_objective=delta(rows[0.],'321'),maximum_score_disagreement=score_error,
                maximum_gradient_disagreement_per_km=gradient_error,finite_step_gradient_disagreement_per_km=finite_step,
                maximum_adaptive_relative_error=adaptive_error,maximum_dense_node_error=dense_error,
                weak_direction_displacement_proxy_km=shift,numerical_displacement_agreement_proxy_km=error,
                material=material,global_mode_certificate=False))
        paired=all(arm['qualified'] for arm in arms)
        decision=('conditional_effect_warrants_review' if paired and any(a.get('material',False) for a in arms)
                  else 'close_tested_conditional_neighborhood_small_effect' if paired
                  else 'close_unresolved_without_optimizer')
        summaries.append(dict(case=case,norad=selected['norad'],arms=arms,paired_resolved=paired,decision=decision))
    out=dict(rows=summaries,cumulative_scientific_seconds=result['cumulative_scientific_seconds'],
        protocol_sha256=sha(HERE/'protocol.json'),RF_seal_sha256=sha(HERE/'RF_seal.json'),
        position_fits=0,GPS_used=False,global_absolute_precision_claim=False)
    with (HERE/'summary.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
