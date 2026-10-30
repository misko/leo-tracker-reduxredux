"""Append training-only predictive views without altering calibration geometry."""
import copy
import numpy as np
from leo.analysis.research.retained_track_likelihood import whitening
from leo.analysis.research.grouped_prediction import replay_split


def predictive_training_views(scan,entries,split,minimum_points=4):
    if minimum_points<4:raise ValueError('at least four training points required')
    changed=copy.copy(scan);changed.tracks=list(scan.tracks);changed.white=list(scan.white);changed.rx_basis=list(scan.rx_basis)
    changed.fixed_window_noise=dict(scan.fixed_window_noise,extra_parameter_BIC_gain=0.)
    changed.radio_sigma_hz=150.;accepted=[];receipts=[]
    for entry in entries:
        i=entry['track_index'];t=scan.tracks[i];train,held=replay_split(t['times'],split)
        receipt=dict(component=entry['component'],source_track_index=i,training_indices=np.flatnonzero(train),
            held_indices=np.flatnonzero(held),training_points=int(train.sum()),held_points=int(held.sum()),
            included=bool(train.sum()>=minimum_points))
        if receipt['included']:
            key=t['key']+'-TRAIN';ids=np.asarray(t['observation_ids'])[train].tolist();times=t['times'][train]
            track=dict(t,key=key,times=times.copy(),values=t['values'][train].copy(),observation_ids=ids,
                start_s=float(times[0]),end_s=float(times[-1]))
            index=len(changed.tracks);changed.tracks.append(track);changed.white.append(whitening(times))
            changed.rx_basis.append(np.asarray(scan.rx_basis[i])[train].copy())
            accepted.append(dict(entry,track_index=index,component=key,points=len(times),observation_ids=ids))
            receipt['training_track_index']=index
        receipts.append(receipt)
    return changed,accepted,receipts
