"""Native-CFO delta injection preserving the original graph/alias coordinates."""
import copy
import hashlib
import json
import numpy as np

PERIOD=1/4.4e-6


def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=encode,allow_nan=False).encode()).hexdigest()


def inject(d,rows,expected_ids):
    """Add native new-minus-old CFO to graph values; never rewrap or reassociate."""
    ids=[r['native_observation_id'] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected_ids):raise ValueError('exact unique selected native-ID vector required')
    observations={o['observation_id']:o for o in d['observations']}
    if len(observations)!=len(d['observations']):raise ValueError('duplicate original native IDs')
    delta={}
    for row in rows:
        oid=row['native_observation_id'];old=float(row['original_cfo_hz']);new=float(row['corrected_cfo_hz'])
        if oid not in observations or observations[oid]['measured_cfo_hz']!=old:raise ValueError('original native CFO differs')
        if not np.isfinite([old,new]).all():raise ValueError('finite CFO required')
        if not row['numerical_frequency_qualified'] and new!=old:raise ValueError('unqualified correction must be exact baseline')
        delta[oid]=new-old
    scan=copy.copy(d['scan']);scan.tracks=[];seen=set();coordinate=[]
    for track in d['scan'].tracks:
        copied=dict(track);copied['values']=np.asarray(track['values'],float).copy()
        for index,oid in enumerate(track['observation_ids']):
            if oid not in observations:raise ValueError('graph ID missing from native ledger')
            offset=float(track['values'][index]-observations[oid]['measured_cfo_hz'])
            if abs(offset/PERIOD-round(offset/PERIOD))>1e-10:raise ValueError('graph/native coordinate is not fixed integer alias')
            if oid in delta:
                copied['values'][index]+=delta[oid];seen.add(oid)
                coordinate.append(dict(native_observation_id=oid,component=track['key'],index=index,
                    graph_native_offset_hz=offset,integer_graph_lift=int(round(offset/PERIOD)),
                    delta_hz=delta[oid],original_graph_value_hz=float(track['values'][index]),
                    corrected_graph_value_hz=float(copied['values'][index])))
        scan.tracks.append(copied)
    if seen!=set(delta):raise ValueError('selected native ID is absent from graph')
    updated=[dict(o,measured_cfo_hz=float(o['measured_cfo_hz']+delta[o['observation_id']]))
             if o['observation_id'] in delta else dict(o) for o in d['observations']]
    changed=dict(d,scan=scan,observations=updated)
    all_nonselected_exact=True
    for old,new in zip(d['scan'].tracks,scan.tracks,strict=True):
        for index,oid in enumerate(old['observation_ids']):
            if oid not in delta and old['values'][index]!=new['values'][index]:all_nonselected_exact=False
        if not np.array_equal(old['times'],new['times']):raise ValueError('times changed')
    if not all_nonselected_exact:raise ValueError('nonselected observations changed')
    immutable=('node','keep','powers','means','model','entries')
    if any(digest(d[k])!=digest(changed[k]) for k in immutable):raise ValueError('inference contract changed')
    receipt=dict(native_IDs=sorted(delta),native_IDs_sha256=digest(sorted(delta)),
        native_delta_sha256=digest(sorted(delta.items())),coordinate_rows=coordinate,
        nonselected_graph_values_exact=all_nonselected_exact,original_native_IDs_exact=True,
        unchanged_inference_fingerprint=digest({k:d[k] for k in immutable}),
        unchanged_graph_metadata_fingerprint=digest([{k:v for k,v in t.items() if k!='values'} for t in scan.tracks]),
        unchanged_noise_fingerprint=digest(scan.fixed_window_noise),
        zero_delta=all(v==0 for v in delta.values()),native_delta_sign='+new_minus_old')
    return changed,receipt
