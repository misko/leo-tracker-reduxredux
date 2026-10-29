"""Validate an omitted native branch and expose it as predictive-only evidence."""
import copy
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.retained_track_likelihood import whitening,projected_receiver_basis,PERIOD


def validated_native_source(validation, explicit=None):
    """Bind a new inclusion to the exact discovery file used for its annotation."""
    receipt=read(Path(validation)/'protocol.json')['target']
    if not receipt.get('native_branch_source') or not receipt.get('native_branch_sha256'):
        raise ValueError('annotation lacks native discovery provenance')
    path=Path(explicit) if explicit is not None else Path(receipt['native_branch_source'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['native_branch_sha256']:
        raise ValueError('native discovery differs from annotated source')
    return path


def append_branch(scan,branch,observations,occupied):
    ids=branch['observation_ids'];lookup={o['observation_id']:o for o in observations}
    if len(ids)!=len(set(ids)) or set(ids)&set(occupied):raise ValueError('native branch repeats or overlaps existing graph/associations')
    if not set(ids)<=set(lookup):raise ValueError('native branch contains unknown IDs')
    original=[lookup[o] for o in ids];t=np.asarray(branch['times_s']);y=np.asarray(branch['values_hz']);lifts=np.asarray(branch['alias_lifts'])
    if not np.array_equal(t,[o['time_s'] for o in original]) or np.any(np.diff(t)<=0):raise ValueError('native branch timestamps differ or are not increasing')
    if not np.allclose(y,np.array([o['measured_cfo_hz'] for o in original])+PERIOD*lifts,rtol=0,atol=1e-7):raise ValueError('native branch changes measured CFO')
    if any((o['receiver'],o['channel'],o['actual_rf_hz'])!=(branch['receiver'],branch['channel'],branch['rf_hz']) for o in original):raise ValueError('native branch mixes RF/RX/channel lanes')
    changed=copy.copy(scan);changed.tracks=list(scan.tracks);changed.white=list(scan.white);changed.rx_basis=list(scan.rx_basis)
    index=len(changed.tracks);key=f"{scan.case}-RX{branch['receiver']}-CH{branch['channel']}-NATIVE-{branch['branch_id']}"
    track=dict(key=key,source_id=scan.case,receiver=branch['receiver'],channel=branch['channel'],bank='CH1-4' if branch['channel']<=4 else 'CH5-8',
        rf_hz=branch['rf_hz'],observation_ids=ids,times=t,values=y,quality_status=branch['quality_status'],pieces=branch['pieces'],
        start_s=float(t[0]),end_s=float(t[-1]),residual_rms_hz=branch['RMS_hz'])
    changed.tracks.append(track);changed.white.append(whitening(t));changed.rx_basis.append(projected_receiver_basis(t))
    # Keep curved, index, times and all calibration arrays unchanged. This
    # appended branch can only use direct-time predictive geometry.
    return changed,index


def native_context(d,inventory,path,branch_id):
    pr=read(path.parent/'protocol.json')
    if pr['job']['job_id']!=inventory['job']['job_id'] or pr.get('scramble_seed') is not None:raise ValueError('native discovery belongs to another scan or a null control')
    for source,digest in pr['input_sha256'].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=digest:raise ValueError('native discovery input changed')
    branch=next(b for b in read(path)['branches'] if b['branch_id']==branch_id)
    root=Path(inventory['job']['root'])/inventory['job']['case'];obs=read(root/'observations.json')
    occupied={o for t in d['scan'].tracks for o in t['observation_ids']}
    occupied.update(o for r in inventory['policy'].values() for o in r['proposed_associated_ids'])
    changed,index=append_branch(d['scan'],branch,obs,occupied)
    target=dict(track_id=branch_id,track_index=index,component=changed.tracks[index]['key'],current_large=branch['large'],
        observation_ids=branch['observation_ids'],native_branch_source=str(path),native_branch_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        original_graph_unchanged=True,native_branch_quality=branch['quality_status'])
    return dict(d,scan=changed),target
