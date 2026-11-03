"""RF-only phase initializers; no prior or likelihood is changed.

Only regional-centre nominations are read. A score gap within the saved pool
is an engineering proposal filter, not verified satellite identity confidence.
"""

import numpy as np


def seed_vectors(labels,means,groups,*,minimum_gap=2*np.log(20),consensus_mad_s=.25):
    labels=list(map(int,labels));means=np.asarray(means,float)
    if means.shape!=(len(labels),) or len(set(labels))!=len(labels) or not np.isfinite(means).all():
        raise ValueError('distinct original satellite labels and finite phase means required')
    proposals={j:[] for j in labels};used=[]
    for group in groups:
        candidates=group['results']['regional_centre']['candidates']
        if len(candidates)<2:continue
        best=candidates[0];gap=candidates[1]['score']-best['score']
        if gap<minimum_gap or not best['relative_residual_noise']['noise_screen_pass']:continue
        for role in ['first','second']:
            label=int(best[role+'_index']);phase=float(best['phase_'+role+'_s'])
            if label in proposals and np.isfinite(phase) and abs(phase)<15:
                proposals[label].append(dict(group=group['group'],phase_s=phase,local_pool_gap=gap))
                used.append((group['group'],label))
    median=np.zeros(len(labels));consensus=np.zeros(len(labels));details=[]
    for k,label in enumerate(labels):
        unique={r['group']:r for r in proposals[label]};values=np.array([r['phase_s'] for r in unique.values()])
        if not len(values):continue
        center=float(np.median(values));mad=float(np.median(abs(values-center)))
        median[k]=center
        coherent=len(values)>=2 and mad<=consensus_mad_s
        if coherent:consensus[k]=center
        details.append(dict(candidate_index=label,median_phase_s=center,MAD_s=mad,
            distinct_groups=len(values),consensus_eligible=coherent,proposals=list(unique.values())))
    return dict(prior_mean=np.clip(means,-15,15),negative_prior_mean=np.clip(-means,-15,15),
        RF_median=median,RF_consensus=consensus,details=details,
        only_initialization_not_prior_or_measurement=True,current_scan_RF_mode_not_used=True)
