import numpy as np


def key(track,i):
    return int(track['receiver_id']),float(track['rf_hz']),int(round(float(track['times_s'][i])*1e9)),int(round(float(track['y'][i])*1e6))


def deduplicate(doc):
    owners={}
    labels={}
    for track in sorted(doc['tracks'],key=lambda t:t['track_id']):
        for i in range(len(track['y'])):
            k=key(track,i)
            if k in labels and labels[k]!=bool(track['mask'][i]):
                raise ValueError('Repeated key crosses train/held split')
            labels[k]=bool(track['mask'][i])
            owners.setdefault(k,track['track_id'])
    tracks,removed=[],[]
    for track in doc['tracks']:
        keep=np.array([owners[key(track,i)]==track['track_id'] for i in range(len(track['y']))])
        for i in np.flatnonzero(~keep):
            removed.append(dict(track_id=track['track_id'],index=int(i),owner=owners[key(track,i)],training=bool(track['mask'][i])))
        copy=dict(track)
        for field in ('times_s','measured_hz','training_mask','y','mask'):
            copy[field]=np.asarray(track[field])[keep].copy()
        for field in ('candidate_position_km','candidate_velocity_km_s'):
            copy[field]=track[field][:,:,keep,:].copy() if not keep.all() else track[field]
        if copy['mask'].sum()<2 or (~copy['mask']).sum()<1:
            raise ValueError(f"Track loses required support: {track['track_id']}")
        tracks.append(copy)
    return dict(doc,tracks=tracks),removed
