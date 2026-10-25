"""Check sign-aware CFO against independent within-frame carrier evidence.

A regular inter-frame phase progression need not be the RF carrier. Both
proposed carriers are estimated from the training frames and scored against
the same free-complex-gain likelihood on the other frames.
"""

import numpy as np


def within_frame_carrier_prediction(workspace,base,result,maximum_loss=9.):
    rows=[]
    for train,test in [('even','odd'),('odd','even')]:
        reference=workspace.frequency_fit(base['CFO_hz'],base['offset_samples'],base['modulation_ppm'],train)
        proposed=result['fits'][train]
        f=np.array([reference['CFO_hz'],proposed['CFO_hz']])
        d=workspace.evaluate(f,base['offset_samples'],base['modulation_ppm'],test,details=True)
        n=sum(len(workspace.frames[k]) for k in d['frames'])
        s=np.maximum(1-d['scores'],1e-15)
        loss=float(2*n*np.log(s[1]/s[0]))
        rows.append(dict(train=train,test=test,training_within_frame_CFO_hz=reference['CFO_hz'],
            training_sign_CFO_hz=proposed['CFO_hz'],heldout_negative_twice_log_likelihood_loss=loss,
            reference_search_boundary=reference['frequency_search_boundary'],heldout_samples=n))
    passed=all(r['heldout_negative_twice_log_likelihood_loss']<=maximum_loss and not r['reference_search_boundary'] for r in rows)
    return dict(folds=rows,passed=passed,maximum_allowed_loss=maximum_loss,
        actual_CFO_not_identified_by_regular_interframe_phase_alone=True,
        timing_and_rate_still_conditioned_on_common_all_frame_RF_fit=True,
        Gaussian_profile_score_not_calibrated_probability=True)
