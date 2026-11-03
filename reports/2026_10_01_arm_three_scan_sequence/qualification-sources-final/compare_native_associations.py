"""Separate exact association choices from numerical score roundoff."""
import math


def compare(actual, reference, tolerance_hz):
    if not math.isfinite(tolerance_hz) or not 0 <= tolerance_hz <= 1e-6:
        raise ValueError('invalid predeclared score tolerance')
    if actual.keys()!=reference.keys() or len(actual['points'])!=len(reference['points']):
        raise ValueError('association point inventory differs')
    ids=True;taus=True;counts=True;deltas=[];track_count=0
    def delta(a,b):
        if not math.isfinite(a) or not math.isfinite(b):raise ValueError('nonfinite association score')
        deltas.append(abs(a-b))
    for a,b in zip(actual['points'],reference['points']):
        if a.keys()!=b.keys() or len(a['tracks'])!=len(b['tracks']):
            raise ValueError('association track inventory differs')
        counts &= a['matched_tracks']==b['matched_tracks']
        delta(a['score_hz'],b['score_hz'])
        for x,y in zip(a['tracks'],b['tracks']):
            if x.keys()!=y.keys():raise ValueError('association fields differ')
            track_count+=1;ids &= x['candidate_id']==y['candidate_id'];taus &= x['tau_s']==y['tau_s']
            for key in ('held_hz','fit_hz','offset_hz'):delta(x[key],y[key])
    maximum=max(deltas,default=0.)
    return {'satellite_choices_exact':ids,'time_offsets_exact':taus,'matched_counts_exact':counts,
        'tracks_compared':track_count,'maximum_numeric_delta_hz':maximum,'exact_json':actual==reference,
        'position_tolerance_hz':tolerance_hz,'within_position_tolerance':ids and taus and counts and maximum<=tolerance_hz}
