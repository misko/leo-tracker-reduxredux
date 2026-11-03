"""Test transfer of a common native-Hz receiver drift between satellites."""

import csv
import json
from pathlib import Path

import numpy as np

from residual_trend_audit import CARRIER, OUTPUT, file_digest, regress, rms, serializable, stats


def shared_design(times, channels, track_ids, order):
    levels=np.unique(track_ids)
    channel_levels=np.unique(channels)
    return np.column_stack([track_ids==t for t in levels]+
        [channels==c for c in channel_levels[1:]]+
        [((times-150)/100)**k for k in range(1,order+1)])


def transferred_component(train_times, train_ch, train_tracks, train_y, test_times, test_ch, order):
    design=shared_design(train_times,train_ch,train_tracks,order)
    coef,_,rank=regress(design,train_y)
    if rank!=design.shape[1]:return None
    channel_levels=np.unique(train_ch)
    if not np.isin(test_ch,channel_levels).all():return None
    off=len(np.unique(train_tracks));nchannel=len(channel_levels)-1
    output=np.zeros(len(test_times))
    for i,c in enumerate(channel_levels[1:]):output+=(test_ch==c)*coef[off+i]
    for k in range(1,order+1):output+=coef[off+nchannel+k-1]*((test_times-150)/100)**k
    return output


def run():
    path=OUTPUT/'points-and-diagnostic-corrections.csv'
    dest=OUTPUT/'shared-receiver-drift.json'
    if dest.exists():raise FileExistsError(dest)
    with path.open() as stream:rows=list(csv.DictReader(stream))
    results=[]
    for scan in 'AB':
        for rx in (0,1):
            subset=[r for r in rows if r['scan']==scan and int(r['receiver'])==rx]
            times=np.array([float(r['time_s']) for r in subset]);ch=np.array([int(r['channel']) for r in subset])
            ids=np.array([int(r['catalog_number']) for r in subset]);rf=np.array([float(r['rf_hz']) for r in subset])
            y=np.array([float(r['residual_hz']) for r in subset])*rf/CARRIER
            fits=[]
            for order in (1,2):
                design=shared_design(times,ch,ids,order);co,pred,rank=regress(design,y)
                per=[]
                for target in np.unique(ids):
                    test=ids==target;train=~test
                    component=transferred_component(times[train],ch[train],ids[train],y[train],times[test],ch[test],order)
                    supported=np.min(np.abs(times[test,None]-times[None,train]),axis=1)<=2.0
                    entry={'satellite':int(target),'target_count':int(test.sum()),'same_time_peer_support_count':int(supported.sum())}
                    if component is not None and supported.sum()>=15 and np.ptp(times[test][supported])>=10:
                        v=y[test][supported];e=v-component[supported];x=times[test][supported]
                        entry.update(available=True,baseline_centered_rms_hz=rms(v-v.mean()),
                            corrected_centered_rms_hz=rms(e-e.mean()),before=stats(x,v),after=stats(x,e))
                    else:entry.update(available=False)
                    per.append(entry)
                fits.append({'order':order,'rank':rank,'columns':design.shape[1],'coefficients':co,
                    'track_order':np.unique(ids),'channel_order':np.unique(ch),'in_sample_rms_hz':rms(y-pred),
                    'leave_satellite_out_shape_transfer':per})
            results.append({'scan':scan,'receiver':rx,'fits':fits})
    result={'source_hashes':{str(path):file_digest(path),str(Path(__file__)):file_digest(__file__)},'receivers':results,
        'model':'Native-RF Hz residual = per-track constant + common receiver/channel constants + common receiver polynomial in actual receive time. All sealed orbit/timing parameters fixed.',
        'validation':'Exclude target satellite from fitting shared drift. Test only where a different satellite on the same receiver has an observation within 2 s (not necessarily same channel). Remove each test residual mean before scoring, so this is a conditional shape-transfer diagnostic, not absolute held-out frequency prediction.',
        'limitations':'Receiver is confounded with which satellites are visible at each time. A failed shared polynomial rejects that simple model, not every possible common oscillator process. Same-time, same-channel differencing in the main receipt is the stronger cancellation control.'}
    dest.write_text(json.dumps(serializable(result),indent=2,allow_nan=False)+'\n')
    for r in results:
        for f in r['fits']:
            print(r['scan'],r['receiver'],f['order'],[(p['satellite'],round(p['baseline_centered_rms_hz'],1),round(p['corrected_centered_rms_hz'],1)) for p in f['leave_satellite_out_shape_transfer'] if p['available']])


if __name__=='__main__':run()
