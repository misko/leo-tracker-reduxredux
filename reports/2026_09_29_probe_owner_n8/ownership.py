import numpy as np


def resolve(doc,quality):
    groups={}
    for track in doc['tracks']:
        points=sorted([r for r in quality if r['track_id']==track['track_id']],key=lambda r:r['index'])
        assert [r['index'] for r in points]==list(range(len(track['y'])))
        assert [r['training'] for r in points]==track['mask'].tolist()
        groups[track['track_id']]=[r['source_group_id'] for r in points]
        assert len(groups[track['track_id']])==len(set(groups[track['track_id']]))
    owners={}
    for track in sorted(doc['tracks'],key=lambda t:(-int(t['mask'].sum()),t['track_id'])):
        for g in groups[track['track_id']]:owners.setdefault(g,track['track_id'])
    retained=[];ledger=[];used=[]
    for track in doc['tracks']:
        gg=groups[track['track_id']]
        keep=np.array([owners[g]==track['track_id'] for g in gg])
        copy=dict(track)
        for field in ('times_s','measured_hz','training_mask','y','mask'):
            copy[field]=np.asarray(track[field])[keep].copy()
        for field in ('candidate_position_km','candidate_velocity_km_s'):
            copy[field]=track[field][:,:,keep,:].copy() if not keep.all() else track[field]
        train=int(copy['mask'].sum());held=int((~copy['mask']).sum())
        passed=train>=2 and held>=1
        ledger.append(dict(track_id=track['track_id'],removed_indices=np.flatnonzero(~keep).tolist(),retained_training=train if passed else 0,retained_held=held if passed else 0,owned_training=train,owned_held=held,excluded=not passed,reason=None if passed else 'insufficient_support_after_ownership'))
        if passed:
            retained.append(copy);used.extend(g for g,k in zip(gg,keep,strict=True) if k)
    assert len(used)==len(set(used))
    if not retained:raise ValueError('No eligible track remains in scan')
    return dict(doc,tracks=retained),dict(tracks=ledger,original_groups=len(owners),retained_groups=len(used),unrepresented_groups=len(owners)-len(used))
