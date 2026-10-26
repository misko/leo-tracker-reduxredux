"""Timing-bank nomination on disjoint random native frame groups.

Own GLRT64 algebra, public templates/fractional sampling; no private scorer or
frequency posterior. The historical 512-bin frequency winner is preserved.
"""
import hashlib
import json
import math
import numpy as np
from leo.analysis.starlink.fast_scan_fractional import fractional_take, fractional_take_bounds
from leo.analysis.starlink.templates import qin_edge_pilot_frame, CONTROL_SYMBOL_ROLL

VERSION='missed-visit-timing-v1'
COARSE=np.arange(-256,257,8,dtype=int)
FINE=np.arange(-8,9,dtype=int)
MODE_CAP=8
GATE=.025
SEED=2026102603


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def partition(length,rate,epoch,owner):
    """Partition native intervals before sample values; same for every mode."""
    period=rate/750.;origin=epoch-period/2
    intervals=[]
    for k in range(-2,int(length/period)+3):
        start=math.ceil(origin+k*period);stop=math.ceil(origin+(k+1)*period)
        if 0<=start<stop<=length:
            intervals.append(dict(frame_id=k,start=start,stop=stop))
    if len(intervals)<8:raise ValueError('fewer than eight complete native intervals')
    order=sorted(intervals,key=lambda x:hashlib.sha256(f'{SEED}/{owner}/{x["frame_id"]}'.encode()).hexdigest())
    search={x['frame_id'] for x in order[:len(order)//2]}
    for interval in intervals:interval['group']='search' if interval['frame_id'] in search else 'confirmation'
    return dict(seed=SEED,owner=owner,origin_samples=origin,period_samples=period,intervals=intervals,
        independent_observations=0,assignment_uses_sample_values=False)


def cache_for_group(samples,fraction,ownership,group):
    """Read only the requested group's taps, including interpolation guards."""
    values=np.asarray(samples,complex);cached=np.full(len(values),np.nan+1j*np.nan)
    left,right=fractional_take_bounds(fraction)
    intervals=ownership['intervals'] if group!='all' else [dict(start=0,stop=len(values),group='all')]
    for interval in intervals:
        if group!='all' and interval['group']!=group:continue
        indexes=np.arange(interval['start']+left,interval['stop']-right,dtype=int)
        if len(indexes):cached[indexes]=fractional_take(values,indexes.astype(float)+fraction)
    return cached


def geometry(length,rate,epoch,ownership,group):
    period=rate/750.;integer=math.floor(epoch);fraction=epoch-integer
    left,right=fractional_take_bounds(fraction);rows=[]
    for frame in range(int(length/period)+2):
        frame_start=integer+round(frame*period)
        # Symbols2..65, each44samples; min/max include every Lanczos tap.
        start=frame_start+88-left;stop=frame_start+2904+right
        if start<0 or stop>length:continue
        interval=next((i for i in ownership['intervals'] if i['start']<=start and stop<=i['stop']),None)
        if group!='all' and (interval is None or interval['group']!=group):continue
        rows.append(dict(frame=frame,frame_start=frame_start,interval_id=interval['frame_id'] if interval else None,
            sample_start=start,sample_stop=stop))
    return rows


def scores(samples,rate,edge,mode,offsets,ownership,group,cache=None):
    """Batch bounded offsets; unchanged exact/control coherence and CFO grid."""
    if rate!=10_000_000:raise ValueError('frozen native rate is10MHz')
    values=np.asarray(samples,complex)
    base=float(mode['epoch_samples']);fraction=base-math.floor(base)
    key=(float(fraction),group)
    cache={} if cache is None else cache
    if key not in cache:cache[key]=cache_for_group(values,fraction,ownership,group)
    source=cache[key]
    relative=np.arange(2,66)[:,None]*44+np.arange(44)[None,:]
    exact=np.asarray(qin_edge_pilot_frame(rate,edge),complex)[relative]
    control=np.asarray(qin_edge_pilot_frame(rate,edge,symbol_roll=CONTROL_SYMBOL_ROLL),complex)[relative]
    reference_time=float(mode['reference_offset_s'])
    predicted=float(mode['cfo_hz']);cfo_rate=float(mode.get('cfo_rate_hz_s',0.))
    frequency_grid=np.fft.fftfreq(512,d=44/rate)
    result=[]
    for block in range(0,len(offsets),8):
        offsets_chunk=[int(x) for x in offsets[block:block+8]];positions=[];belongs=[];geometries=[]
        for j,offset in enumerate(offsets_chunk):
            epoch=(base+offset)%(rate/750.)
            # Native modulo is nonintegral; each wrap changes fraction. Preserve
            # its exact fraction and cache rather than rounding the epoch.
            frac=epoch-math.floor(epoch);chunk_key=(float(frac),group)
            if chunk_key not in cache:cache[chunk_key]=cache_for_group(values,frac,ownership,group)
            rows=geometry(len(values),rate,epoch,ownership,group);geometries.append((epoch,frac,rows,chunk_key))
            for row in rows:
                positions.append(row['frame_start']+relative);belongs.append(j)
        if positions:
            indexes=np.asarray(positions);belongs=np.asarray(belongs,dtype=int)
            received=np.empty(indexes.shape,complex);absolute=np.empty(indexes.shape,float)
            for j,(epoch,frac,rows,chunk_key) in enumerate(geometries):
                chosen=np.flatnonzero(belongs==j)
                if len(chosen):
                    received[chosen]=cache[chunk_key][indexes[chosen]]
                    absolute[chosen]=indexes[chosen]+frac
            if not np.all(np.isfinite(received)):raise ValueError('group sample or interpolation ownership leak')
            frame_times=np.mean(absolute,axis=(1,2))/rate
            frame_cfo=predicted+cfo_rate*(frame_times-reference_time)
            corrected=received*np.exp(-2j*np.pi*frame_cfo[:,None,None]*absolute/rate)
            ce=np.sum(np.conj(exact)[None,:,:]*corrected,axis=2)
            cc=np.sum(np.conj(control)[None,:,:]*corrected,axis=2)
            exact_power=abs(np.fft.fft(ce,n=512,axis=1))**2
            control_power=abs(np.fft.fft(cc,n=512,axis=1))**2
            exact_ceiling=np.sum(abs(ce),axis=1)**2;control_ceiling=np.sum(abs(cc),axis=1)**2
        for j,(epoch,frac,rows,chunk_key) in enumerate(geometries):
            offset=offsets_chunk[j]
            if len(rows)<2:
                result.append(dict(offset_samples=offset,epoch_samples=epoch,status='insufficient_group_frames',frames=len(rows),margin=None));continue
            chosen=np.flatnonzero(belongs==j)
            pe=np.sum(exact_power[chosen],axis=0)/max(float(np.sum(exact_ceiling[chosen])),1e-300)
            pc=np.sum(control_power[chosen],axis=0)/max(float(np.sum(control_ceiling[chosen])),1e-300)
            best=int(np.argmax(pe));exact_score=float(pe[best]);control_score=float(np.max(pc))
            result.append(dict(offset_samples=offset,epoch_samples=float(epoch),status='complete',
                frames=len(rows),exact_score=exact_score,control_score=control_score,margin=exact_score-control_score,
                residual_cfo_hz=float(frequency_grid[best]),tracking_cfo_hz=predicted+float(frequency_grid[best]),
                cfo_reference_offset_s=reference_time,cfo_rate_hz_s=cfo_rate,
                frame_interval_ids=[r['interval_id'] for r in rows]))
    return result


def rank_key(candidate):
    return (-candidate['score']['margin'],candidate['mode_index'],abs(candidate['score']['offset_samples']),candidate['score']['offset_samples'])


def confirmed(score,mode,search_score):
    if score['status']!='complete':return dict(pilot_confirmed=False,continuity_compatible=False,admitted=False)
    width=float(mode['cfo_half_width_hz'])
    compatible=abs(score['tracking_cfo_hz']-mode['cfo_hz'])<=width
    search_pass=search_score['margin'] is not None and search_score['margin']>=GATE
    return dict(pilot_confirmed=bool(score['margin']>=GATE),
        continuity_compatible=bool(compatible),earlier_cfo_half_width_hz=width,
        cfo_prediction_residual_hz=score['tracking_cfo_hz']-mode['cfo_hz'],
        search_confirm_CFO_difference_hz=score['tracking_cfo_hz']-search_score['tracking_cfo_hz'],
        search_passed_gate=bool(search_pass),
        admitted=bool(score['margin']>=GATE and compatible),
        new_independent_Doppler_points=0,uncertainty_weights_qualified=False)


def score_target(samples,rate,edge,packet,on_selected=None):
    modes=packet['modes'];support=packet['target_support']
    if len(samples)!=support['stop_counter']-support['start_counter']:raise ValueError('native support length mismatch')
    if len(modes)>MODE_CAP:raise ValueError('mode cap exceeded; do not silently truncate')
    out=dict(schema=VERSION,owner_id=packet['owner_id'],target_support=support,
        status='no_donor' if not modes else 'started',mode_provenance=modes,
        exposure=[],point=None,search=None,uncertainty_weights_qualified=False)
    if not modes:return out
    for mode in modes:
        if not mode['donors']:raise ValueError('donor provenance absent')
        for donor in mode['donors']:
            if donor['support']['stop_counter']>support['start_counter']:raise ValueError('donor overlaps target')
    ownership=partition(len(samples),rate,modes[0]['epoch_samples'],packet['owner_id'])
    out['ownership']=ownership;cache={};candidates=[];point_candidates=[]
    for i,mode in enumerate(modes):
        bank=scores(samples,rate,edge,mode,COARSE,ownership,'search',cache)
        for score in bank:
            candidate=dict(mode_index=i,mode_id=mode['mode_id'],stage='coarse',score=score)
            out['exposure'].append(candidate)
            if score['status']=='complete':candidates.append(candidate)
            if score['offset_samples']==0 and score['status']=='complete':point_candidates.append(candidate)
    if not candidates:out['status']='no_search_support';return out
    coarse=min(candidates,key=rank_key);i=coarse['mode_index'];mode=modes[i]
    fine_offsets=sorted(set(int(np.clip(coarse['score']['offset_samples']+x,-256,256)) for x in FINE))
    fine=scores(samples,rate,edge,mode,fine_offsets,ownership,'search',cache)
    for score in fine:
        candidate=dict(mode_index=i,mode_id=mode['mode_id'],stage='fine',score=score)
        out['exposure'].append(candidate)
        if score['status']=='complete':candidates.append(candidate)
    selected=min(candidates,key=rank_key);i=selected['mode_index'];mode=modes[i]
    point_selected=min(point_candidates,key=rank_key) if point_candidates else None
    receipt=dict(owner_id=packet['owner_id'],selected=selected,point_selected=point_selected,ownership=ownership,
        target_support=support,confirmation_accessed=False,source_version=VERSION,
        earlier_packet_sha256=digest(packet))
    receipt['selection_sha256']=digest(receipt)
    if on_selected is not None:on_selected(receipt)
    # Confirmation is not evaluated until after the above receipt is sealed.
    selected_score=scores(samples,rate,edge,mode,[selected['score']['offset_samples']],ownership,'confirmation',cache)[0]
    out['selection_receipt']=receipt
    out['search']=dict(selected=selected,confirmation=selected_score,
        evaluation=confirmed(selected_score,mode,selected['score']),
        native_confirmation_blocks=geometry(len(samples),rate,selected_score['epoch_samples'],ownership,'confirmation'),
        native_search_blocks=geometry(len(samples),rate,selected_score['epoch_samples'],ownership,'search'))
    if point_selected is not None:
        point_mode=modes[point_selected['mode_index']]
        point_score=scores(samples,rate,edge,point_mode,[0],ownership,'confirmation',cache)[0]
        out['point']=dict(selected=point_selected,search=point_selected['score'],confirmation=point_score,
            evaluation=confirmed(point_score,point_mode,point_selected['score']),
            native_confirmation_blocks=geometry(len(samples),rate,point_score['epoch_samples'],ownership,'confirmation'))
    out['status']='complete'
    return out
