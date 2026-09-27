"""Pure checks for canonical CFO unwrapping and cross-channel shape agreement."""
from bisect import bisect_left
import math
import statistics


def alias_check(rows,canonical_rf_hz=11_200_000_000.,spacing_hz=1/4.4e-6):
    indices=[];errors=[]
    for r in rows:
        scale=canonical_rf_hz/r['actual_rf_hz']
        value=(r['source_cfo_hz']*scale-r['normalized_cfo_hz'])/(spacing_hz*scale)
        if not math.isfinite(value):raise ValueError('nonfinite alias')
        indices.append(round(value));errors.append(abs(value-round(value)))
    if max(errors)>1e-8:raise ValueError('CFO does not match integer alias normalization')
    return {'alias_indices':indices,'maximum_integer_discrepancy':max(errors),
            'alias_changes':sum(a!=b for a,b in zip(indices,indices[1:]))}


def cross_channel_difference(left,right,max_gap_s=1.5):
    """Interpolate only bracketed points, excluding gaps > fixed bound."""
    left=sorted(left,key=lambda r:r['utc_ns']);right=sorted(right,key=lambda r:r['utc_ns'])
    times=[r['utc_ns'] for r in right]
    if len(set(times))!=len(times):raise ValueError('duplicate reference times')
    pairs=[]
    for r in left:
        i=bisect_left(times,r['utc_ns'])
        if i<len(times) and times[i]==r['utc_ns']:
            interpolated=right[i]['normalized_cfo_hz'];gap=0.
        elif 0<i<len(times):
            a,b=right[i-1],right[i];gap=(b['utc_ns']-a['utc_ns'])/1e9
            if gap>max_gap_s:continue
            f=(r['utc_ns']-a['utc_ns'])/(b['utc_ns']-a['utc_ns'])
            interpolated=a['normalized_cfo_hz']+f*(b['normalized_cfo_hz']-a['normalized_cfo_hz'])
        else:continue
        pairs.append({'utc_ns':r['utc_ns'],'difference_hz':r['normalized_cfo_hz']-interpolated,'bracket_gap_s':gap})
    if not pairs:return {'supported':False,'points':0}
    offsets=[r['difference_hz'] for r in pairs];mean=statistics.mean(offsets)
    return {'supported':True,'points':len(pairs),'constant_difference_hz':mean,
            'difference_rms_after_constant_hz':math.sqrt(statistics.mean((x-mean)**2 for x in offsets)),
            'max_bracket_gap_s':max(r['bracket_gap_s'] for r in pairs),'pairs':pairs}
