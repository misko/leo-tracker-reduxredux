"""Report03: distinguish the old quadrature guard from stronger new assurance."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds24-nomination-information-r01/nomination')
CASES=('DS24-0010','DS24-0011');ARMS=('c0','fitted_c')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def report():
    seal=read(HERE/'RF_seal.json')
    for path,digest in seal['files'].items():
        if sha(path)!=digest:raise ValueError('scientific artifact changed: '+path)
    rows=[];candidate_rows=[]
    for case in CASES:
        for trial in range(6):
            truth=read(OLD/case/f'trial{trial}'/'generation.json');kind=truth['kind'];true=truth['generating_norad']
            for arm in ARMS:
                path=HERE/case/f'trial{trial}'/(arm+'_result.json')
                old=read(OLD/case/f'trial{trial}'/(arm+'_result.json'))
                try:result=read(path) if path.exists() else None
                except (ValueError,OSError):result=None
                row=dict(case=case,trial=trial,arm=arm,kind=kind,generating_norad=true,
                    status='unavailable',absolute_precision_qualified=False,model_order_proved=False,
                    old_quadrature_guard_passed=old['ordering_numerically_qualified'],
                    failure_class='budget/context result unavailable',
                    certified_winner_kind=None,certified_winner_norad=None,raw_best_physical_norad=None,
                    raw_physical_minus_null=None,raw_truth_best=None,raw_preference=None)
                if result is not None:
                    proof=result['evidence_order_certificate'];gap=result['physical_minus_null']
                    row.update(status=result['status'],absolute_precision_qualified=result['ordering_numerically_qualified'],
                        old_quadrature_guard_passed=result['old_ordering_numerically_qualified'],
                        model_order_proved=proof['proved'],certified_winner_kind=proof.get('winner_kind'),
                        certified_winner_norad=proof.get('winner_norad'),raw_best_physical_norad=result['winner_norad'],
                        raw_physical_minus_null=gap,raw_truth_best=result['winner_norad']==true if true is not None else None,
                        raw_preference=('physical' if gap<0 else 'unresolved') if gap is not None else None,
                        null_reference_error=result['null']['independent_dense_error'],
                        null_reference_passed=result['null']['independent_dense_passed'],
                        order_failure_reason=proof.get('reason'),model_order_margin=proof.get('minimum_log_evidence_margin'),
                        failure_class=('null-reference arithmetic guard' if not result['null']['independent_dense_passed'] else
                            'evidence/support bound unresolved' if not proof['proved'] else 'none'),
                        certified_winner_disagrees_with_generator=bool(proof['proved'] and
                            (proof.get('winner_norad')!=true if kind=='physical' else proof.get('winner_kind')!='unresolved')))
                    for candidate in result['candidates']:
                        bounds=candidate.get('physical_enclosure',{})
                        candidate_rows.append(dict(case=case,trial=trial,arm=arm,norad=candidate['norad'],status=candidate['status'],
                            old_objective=candidate.get('old_objective'),new_objective=candidate.get('objective'),
                            new_minus_old=candidate.get('new_minus_old_objective'),change_category=candidate.get('change_category'),
                            absolute_precision_qualified=candidate.get('numerically_qualified'),
                            mode_and_support_qualified=candidate.get('mode_and_support_qualified'),
                            score_distance_to_full_enclosure=candidate.get('objective_distance_to_full_enclosure'),
                            inner_envelope_objective_width=bounds.get('objective_width'),panels=bounds.get('panels'),
                            envelope_exclusion_stop=bounds.get('stopped_for_certified_exclusion'),
                            visible_prior_mass=candidate.get('inner_visible_prior_mass'),root_bracket_prior_mass=candidate.get('root_bracket_prior_mass'),
                            primary_success=candidate.get('primary',{}).get('success'),
                            primary_reference_error=candidate.get('primary_reference_error'),
                            independent_reference_success=candidate.get('independent_reference',{}).get('success'),
                            failure=candidate.get('error')))
                else:
                    # Preserve all192 predeclared candidate contexts. Partial
                    # checkpoints remain diagnostic, never silently promoted to
                    # a completed ordering or omitted from the denominator.
                    screen=read(OLD/case/f'trial{trial}'/'screen.json')
                    for norad in screen['candidate_norads']:
                        checkpoint=HERE/case/f'trial{trial}'/(arm+'_'+str(norad)+'_checkpoint.json')
                        try:saved=read(checkpoint) if checkpoint.exists() else {}
                        except (ValueError,OSError):saved={'error':'interrupted checkpoint bytes preserved'}
                        candidate_rows.append(dict(case=case,trial=trial,arm=arm,norad=norad,
                            status='partial_checkpoint' if saved else 'unavailable_budget_or_context',
                            new_objective=saved.get('objective'),absolute_precision_qualified=False,
                            mode_and_support_qualified=saved.get('mode_and_support_qualified'),
                            failure='no terminal arm ordering; partial science retained' if saved else 'not reached within frozen execution'))
                rows.append(row)
    output=HERE/'report03';output.mkdir(exist_ok=False)
    write_csv(output/'outcomes.csv',rows);write_csv(output/'candidate_details.csv',candidate_rows)
    summaries=[]
    for arm in ARMS:
        for kind in ('physical','unresolved'):
            subset=[q for q in rows if q['arm']==arm and q['kind']==kind]
            summaries.append(dict(arm=arm,kind=kind,selected=len(subset),complete=sum(q['status']=='complete' for q in subset),
                absolute_precision=sum(q['absolute_precision_qualified'] for q in subset),
                old_quadrature_guard_passed=sum(q['old_quadrature_guard_passed'] for q in subset),
                order_proved=sum(q['model_order_proved'] for q in subset),
                correctly_ordered=sum(q['model_order_proved'] and (q['certified_winner_norad']==q['generating_norad'] if kind=='physical' else q['certified_winner_kind']=='unresolved') for q in subset),
                raw_truth_best=sum(q['raw_truth_best'] is True for q in subset) if kind=='physical' else None,
                raw_expected_model_preference=sum(q['raw_preference']==kind for q in subset)))
    execution=read(HERE/'execution.json')
    summary=dict(summaries=summaries,total_trial_denominator=12,total_arm_denominator=24,
        selected_candidate_contexts=192,reported_candidate_contexts=len(candidate_rows),
        terminal_candidate_contexts=sum(q['status'] in ('complete','zero_physical_evidence','failed') for q in candidate_rows),
        scientific_seconds=execution['total_scientific_seconds'],wall_seconds=execution['wall_seconds'],
        no_fresh_draws_or_position_fits=True,identity_operationally_assigned=False,
        comparison_limit='Old quadrature guard and new physical-envelope precision/order assurance are different criteria, not an apples-to-apples success rate',
        complete=sum(q['status']=='complete' for q in rows),RF_seal_sha256=sha(HERE/'RF_seal.json'))
    with (output/'summary.json').open('x') as f:json.dump(summary,f,indent=2,allow_nan=False)
    fig,axes=plt.subplots(1,2,figsize=(9,4),constrained_layout=True)
    for ax,kind in zip(axes,('physical','unresolved'),strict=True):
        sub=[q for q in summaries if q['kind']==kind];x=np.arange(2)
        ax.bar(x-.3,[q['old_quadrature_guard_passed'] for q in sub],.2,label='Old quadrature guard (different assurance)')
        ax.bar(x-.1,[q['absolute_precision'] for q in sub],.2,label='New event law: precision ≤0.001')
        ax.bar(x+.1,[q['order_proved'] for q in sub],.2,label='New event law: best-model order proved')
        ax.bar(x+.3,[q['selected'] for q in sub],.2,color='gray',alpha=.35,label='All selected (failures retained)')
        ax.set_xticks(x,ARMS);ax.set_ylim(0,max(q['selected'] for q in sub)+1);ax.set_ylabel('Trials');ax.set_title(kind+' controls')
        ax.set_yticks(range(max(q['selected'] for q in sub)+1))
    axes[0].legend(fontsize=6);fig.suptitle('Same 12 observations; changed visibility law and assurance, no identity qualification')
    fig.savefig(output/'precision_vs_order.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True)
    for i,arm in enumerate(ARMS):
        subset=[q for q in rows if q['arm']==arm and q['raw_physical_minus_null'] is not None]
        x=np.array([CASES.index(q['case'])*6+q['trial'] for q in subset])+(i-.5)*.18
        ax.scatter(x,[q['raw_physical_minus_null'] for q in subset],marker=('o','x')[i],label=arm)
    ax.axhline(0,color='k',lw=.7);ax.set_yscale('symlog',linthresh=10)
    ax.set_xticks(range(12),[f'{case[-4:]}/{trial}' for case in CASES for trial in range(6)],rotation=45)
    ax.set_ylabel('Best physical minus polynomial-null objective');ax.set_xlabel('Frozen old trial; each layout has physical0–3 and null4–5')
    ax.set_title('Raw scores, including every unqualified ordering');ax.legend()
    fig.savefig(output/'raw_model_gaps.png',dpi=160);plt.close(fig)
    files={str(p):sha(p) for p in output.iterdir() if p.is_file()};files[str(Path(__file__))]=sha(Path(__file__))
    with (output/'seal.json').open('x') as f:json.dump(dict(files=files),f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':report()
