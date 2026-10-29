"""Controlled identity-score ablation of saved ordinary mixture predictions."""
import copy
import numpy as np
from leo.analysis.research.grouped_prediction import identity_consensus


def evidence_ablation(result):
    """Preserve candidates, observations and adequacy gates; change only score.

    Training plus conditional-held density is joint evidence only for ordinary
    Gaussian-mixture conditioning. Modular cut predictions are rejected.
    Summaries do not multiply overlapping partitions or assert identity truth.
    """
    revised=copy.deepcopy(result)
    name=result['identity_score_name']
    for fold in revised['folds']:
        for proposal in fold['proposals']:
            for arm in ('c0','fitted_c'):
                row=proposal['arms'][arm];score=row['scores'][name]
                if score.get('receiver_posterior_frozen') or score.get('prediction_kind'):
                    raise ValueError('joint decomposition requires ordinary mixture prediction')
                held=float(score['negative_twice_log_density'])
                training=float(score['training_negative_twice_log_density'])
                if not np.isfinite([held,training]).all():raise ValueError('finite density components required')
                row['scores']['joint_target']=dict(score,negative_twice_log_density=training+held)
                row['scores']['training_target']=dict(score,negative_twice_log_density=training)
    original=identity_consensus(result['folds'],score_name=name)
    joint=identity_consensus(revised['folds'],score_name='joint_target')
    training=identity_consensus(revised['folds'],score_name='training_target')
    revised.update(original_annotation=original,annotation=joint,training_evidence_annotation=training,
        identity_score_name='joint_target',source_identity_score_name=name,
        score_ablation_only=True,independent_validation_of_score_rule=False,
        no_accepted_associations=True,conditional_held_adequacy_gates_unchanged=True)
    return revised
