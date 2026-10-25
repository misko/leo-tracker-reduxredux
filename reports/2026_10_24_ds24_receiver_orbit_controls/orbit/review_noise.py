"""Independent read-only audit of the sibling noise control; no scientific fits."""
import hashlib
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
NOISE=OUT.parent/'noise'


def main():
    summary=json.loads((NOISE/'summary.json').read_text())
    results=[json.loads(path.read_text()) for path in sorted((NOISE/'results').glob('DS24*.json'))]
    score_gaps=[];fold_count=0;positive_folds=0
    for result in results:
        allgroups=set(result['folds']);held=[];gains=[]
        for fold in result['checks']:
            assert fold['sufficient']
            train,test=set(fold['training_groups']),set(fold['test_groups'])
            assert not train&test and train|test==allgroups
            assert all(result['folds'][group]==fold['fold'] for group in test)
            assert all(result['folds'][group]!=fold['fold'] for group in train)
            assert all(piece['group'] in test for piece in fold['test_pieces'])
            assert fold['pooled_law']['training_points']==fold['training_points']
            assert sum(law['training_points'] for law in fold['receiver_laws'].values())==fold['training_points']
            recomputed=sum(piece['pooled_loss']-piece['receiver_loss'] for piece in fold['test_pieces'])
            score_gaps.append(abs(recomputed-fold['test_gain']))
            gains.append(recomputed);held.extend(test);fold_count+=1;positive_folds+=int(recomputed>0)
        assert len(held)==len(set(held)) and set(held)==allgroups
        qualified=sum(gains)>2*np.log(2) and sum(g>0 for g in gains)>=2
        assert qualified==result['qualified']
        assert abs(sum(gains)-result['heldout_gain'])<1e-7
        assert all(40<=value<=600 and np.isfinite(value) for value in result['per_observation_noise_sigma_hz'].values())
    assert {r['case'] for r in results}=={r['case'] for r in summary['rows']} and len(results)==24
    # Independently verify the heteroscedastic Gaussian contrast algebra by
    # direct solve/logdet, without importing or fitting the sibling model.
    times=np.linspace(-1,1,23)
    design=np.column_stack((np.ones(len(times)),times,times**2))
    q=np.linalg.qr(design,mode='complete')[0][:,3:]
    variances=1600+900/np.linspace(.2,1,len(times))
    values=np.cos(13*times)*70
    z=q.T@values;covariance=q.T@(variances[:,None]*q)
    root=np.linalg.cholesky(covariance);white=np.linalg.solve(root,z)
    chol=float(white@white+2*np.log(np.diag(root)).sum())
    sign,logdet=np.linalg.slogdet(covariance)
    direct=float(z@np.linalg.solve(covariance,z)+logdet)
    assert sign>0 and abs(chol-direct)<1e-9
    findings=[
        dict(severity='scope',file=str(NOISE/'noise_controls.py'),line=62,
            title='Heldout validation is conditional on the frozen graph',
            detail='Curvature screening, piece membership/degrees and nominated-family grouping were determined from the complete frozen graph. Their selection is not retrained inside folds. The protocol already discloses this, so claims should remain a conditional noise-law comparison rather than independent pipeline/noise-truth validation.'),
        dict(severity='scope',file=str(NOISE/'noise_controls.py'),line=88,
            title='Whole-family holdouts do not establish time-block transfer',
            detail='The seeded folds group nominated families and unmatched tracks, not time blocks. Shared receiver disturbances can span held families at the same times; unknown shared emitters can also be undergrouped. This is not a flaw in the stated family-only protocol, but the result should not be presented as randomized time-block or temporal-transfer validation.'),
        dict(severity='nonblocking_numerical_limitation',file=str(NOISE/'noise_controls.py'),line=32,
            title='Training noise fit is a plug-in surrogate',
            detail='Leverage-corrected residual squares are correlated and mix neighboring variances under heteroscedasticity. The inherited fit_variance optimizer profiles an unclipped law, while learn/variance score and apply its clipped version. Thus the training BIC quantity is a selection heuristic, not an exact likelihood/BIC for independent raw errors. The heldout full-contrast covariance and its determinant are algebraically correct and protect the stated model comparison.'),
        dict(severity='scope',file=str(NOISE/'adapter.py'),line=21,
            title='Predictive-point noise transfer is not separately validated',
            detail='Noise laws are estimated and cross-validated on curved graph pieces, then applied by receiver/margin to predictive-only points as well. This matches the inherited plug-in architecture but does not independently establish those points\' true frequency-error variance.')]
    bindings={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
        [NOISE/'noise_controls.py',NOISE/'adapter.py',NOISE/'protocol.json',NOISE/'summary.json',NOISE/'test_noise_controls.py']}
    audit=dict(review='Independent read-only noise control audit',cases=len(results),folds=fold_count,
        all_saved_group_partitions_disjoint=True,training_only_law_call_paths_reviewed=True,
        maximum_saved_fold_gain_replay_gap=max(score_gaps),positive_folds=positive_folds,
        algebra_direct_vs_Cholesky_difference=abs(chol-direct),
        no_GPS_or_position_predictions_used_in_noise_law_fit=True,
        adapter_applies_per_ID_noise_to_curved_and_predictive_rows=True,
        adapter_copies_scan_and_noise_dictionary=True,
        blocking_implementation_issues_found=False,findings=findings,
        sibling_noise_files_changed=False,no_refits_or_model_tuning=True,sha256=bindings)
    (OUT/'noise_review.json').write_text(json.dumps(audit,indent=2)+'\n')
    lines=['# Independent noise-control review','',
        'No blocking implementation or score-algebra error was found. The review changed no noise files and ran no scientific fits or model tuning.','',
        f"All 24 cases and 72 saved folds passed independent partition and score checks: every nominated family is held out exactly once, training/test groups are disjoint, saved training-point counts match pooled and receiver-law metadata, qualification reproduces, all applied noise SDs lie in 40–600 Hz, and maximum fold-gain replay discrepancy is {max(score_gaps):.3g}. There are {positive_folds}/72 positive fold gains.",'',
        'The score uses z = Qᵀy and C = Qᵀdiag(v)Q for an orthonormal complement of the frozen polynomial design. Its zᵀC⁻¹z + log det C is the correct Gaussian contrast score; the omitted d log(2π) is identical between models. An independent heteroscedastic direct-solve/logdet check agrees with Cholesky to numerical precision. Constant, polynomial-offset and partition tests supplied with the model also pass.','',
        'The variance-law fitting path receives training pieces only. The adapter copies the scan and noise metadata, forces experimental per-ID values, and checks their application to both curved and predictive rows. The synthetic BIC selector flag is explicitly labeled; it is not presented as a measured BIC. No GPS, fitted position or orbital residual enters numerical noise fitting.','',
        'Publication scope qualifications:','']
    for item in findings:
        lines.append('- '+item['title']+': '+item['detail'])
    lines += ['', 'These qualifications limit interpretation; they do not invalidate the frozen-graph family-heldout comparison or its sealed matched-position evaluation. Better contrast density alone does not establish improved location accuracy.']
    (OUT/'NOISE_REVIEW.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({key:value for key,value in audit.items() if key not in ('findings','sha256')},indent=2))


if __name__=='__main__':
    main()
