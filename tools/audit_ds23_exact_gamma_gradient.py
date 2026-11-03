"""Replay exact-Gamma centre values and saved local finite differences."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import probe_ds23_exact_gamma_gradient as inference
from ds23_exact_gamma_position import integrate
from run_algo01_ds23_sample import ROOT,read,write,sha


def replay(case):
    path=inference.BULK/(case+'.json');saved=read(path)
    if saved['status']!='complete':raise ValueError('Gamma gradient diagnostic incomplete')
    context=inference.context_signed(case)
    if sha(context[-1])!=saved['incumbent_sha256']:raise ValueError('Gamma diagnostic incumbent changed')
    rows=[]
    for arm,record in saved['arms'].items():
        center=next(r for r in record['records'] if r['offset']==[0,0]);prepared,base=inference.prepare_point(context,arm,np.array(center['position']))
        exact=integrate(**prepared,**inference.RULES[0])
        for name in ['curved','joint']:
            if abs(exact[name]['negative_twice_log_evidence']-center['estimates'][0][name]['negative_twice_log_evidence'])>1e-6:
                raise ValueError('Gamma centre integration failed independent replay')
        if abs(base['variational_joint_score']-center['variational_joint_score'])>1e-6:raise ValueError('VB centre changed')
        diagnostics=record['diagnostics'];reliable=all(d['minimum_effective_sample_fraction']>=.1 and d['maximum_single_importance_weight']<.05 for d in diagnostics[1:])
        difference=float(np.linalg.norm(np.array(diagnostics[1]['predicted_position_change_from_gap_km'])-np.array(diagnostics[2]['predicted_position_change_from_gap_km'])))
        if reliable!=record['importance_reliable'] or abs(difference-record['independent_seed_predicted_change_disagreement_km'])>1e-12:raise ValueError('Gamma numerical qualification changed')
        rows.append(dict(case=case,arm=arm,predicted_local_shift_km=diagnostics[1]['predicted_change_norm_km'],
            independent_seed_shift_difference_km=difference,importance_reliable=reliable,
            minimum_effective_sample_fraction=diagnostics[1]['minimum_effective_sample_fraction'],
            maximum_single_weight=diagnostics[1]['maximum_single_importance_weight'],
            curved_ELBO_gap_at_mode=center['estimates'][1]['curved_variational_gap'],
            joint_score_difference_at_mode=center['estimates'][1]['joint_variational_gap'],
            centre_integration_replayed=True,all_grid_orbit_predictions_not_independently_recomputed=True,
            maximum_curved_phase_mean_change_s=max(r['estimates'][1]['maximum_exact_vs_VB_phase_change_s'] for r in record['records']),
            source_sha256=sha(path)))
    return rows


def main():
    protocol=read(inference.OUT/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('Gamma gradient source changed')
    with ProcessPoolExecutor(max_workers=7) as pool:
        rows=[r for f in as_completed([pool.submit(replay,c) for c in protocol['cases']]) for r in f.result()]
    write(inference.OUT/'independent_replay_audit.json',dict(rows=rows,original_fixed_phase_reference_preserved=True,
        all_importance_diagnostics_qualified=all(r['importance_reliable'] for r in rows),
        maximum_predicted_local_shift_km=max(r['predicted_local_shift_km'] for r in rows),
        maximum_independent_seed_shift_disagreement_km=max(r['independent_seed_shift_difference_km'] for r in rows),
        no_position_refit_or_accuracy_improvement_claim=True,no_GPS_or_future_TLE_used=True,
        curved_ELBO_gap_is_a_bound_but_joint_score_difference_need_not_be_nonnegative=True,
        linear_prediction_is_exact_for_same_Gaussian_unseen_noise_moment_model=True,
        generalized_evidence_not_calibrated_probability=True,
        interpretation='local mean-design/gradient diagnostic on7 scans; small predicted shifts do not prove a dataset-wide bound or global multimodal equivalence'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True);cases=protocol['cases']
    for k,arm in enumerate(['c0','fitted_c']):
        rr=[next(r for r in rows if (r['case'],r['arm'])==(case,arm)) for case in cases]
        axes[0].bar(np.arange(len(cases))+(k-.5)*.35,[r['predicted_local_shift_km']*1000 for r in rr],width=.33,label=arm,
                    yerr=[r['independent_seed_shift_difference_km']*1000 for r in rr],capsize=2)
        axes[1].scatter([r['curved_ELBO_gap_at_mode'] for r in rr],[r['predicted_local_shift_km']*1000 for r in rr],label=arm)
    axes[0].set(xticks=np.arange(len(cases)),xticklabels=[c[-4:] for c in cases],xlabel='DS23 scan',ylabel='Predicted local position shift (m)',
                title='Correction gradient after integrating Gamma uncertainty')
    axes[1].set(xlabel='Curved-data ELBO minus estimated marginal score',ylabel='Predicted local position shift (m)',
                title='A normalization gap can be nearly constant over position')
    for ax in axes:ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Does variational integration explain the kilometre-scale position error?\nLocal3×3 grids; phase reference fixed; bars show seed disagreement, not confidence intervals; no position adopted')
    fig.savefig(inference.OUT/'approximation_gradient_diagnostic.png',dpi=160);plt.close(fig)
    print('Maximum predicted shift(m)',max(r['predicted_local_shift_km'] for r in rows)*1000,
          'maximum seed difference(m)',max(r['independent_seed_shift_difference_km'] for r in rows)*1000,flush=True)


if __name__=='__main__':main()
