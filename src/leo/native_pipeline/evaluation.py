"""Independent membership evaluation; never imported by native algorithms."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from . import membership as m


def evaluate(observations, sources, tracks, reference_observations,
             reference_sources, reference_tracks, settings, excluded=()):
    obs = m.read_observations(Path(observations))
    src = m.read_sources(Path(sources), obs)
    so = m.read_observations(Path(reference_observations))
    ss = m.read_sources(Path(reference_sources), so)
    out = m.read_tracks(Path(tracks), obs)
    refs = m.read_tracks(Path(reference_tracks), so)
    excluded = set(excluded)
    if not excluded <= {r.index for r in refs.values}:
        raise ValueError('unknown excluded reference')
    eligible = replace(refs, values=tuple(r for r in refs.values if r.index not in excluded))
    full = m.compare(eligible, out, so, obs, ss, src, settings)
    represented = set(full['primary']['reference_segments_with_any_complete_output_indexes'])
    supported = set()
    for tr in out.values:
        if any(r.lane == tr.lane and m.membership_metrics(r,tr,so,obs,ss,src,settings)
               ['consistent_source_count'] for r in refs.values):
            supported.add(tr.index)
    buckets = {}
    for label,lo,hi in [('short',0,15),('medium',15,30),('long',30,float('inf'))]:
        ids = {r.index for r in eligible.values if lo <= (r.end_ns-r.start_ns)/1e9 < hi}
        buckets[label] = {'matched':len(ids & represented), 'total':len(ids)}
    summary = {'strict_represented':len(represented), 'eligible_references':len(eligible.values),
        'one_to_one':full['primary']['complete_one_to_one_count'],
        'outputs':len(out.values), 'additional_unmatched_outputs':len(full['primary']['unmatched_output_indexes']),
        'outputs_without_any_reference_support':len(out.values)-len(supported),
        'duration_buckets':buckets, 'excluded_reference_ids':sorted(excluded),
        'warning':'Reference agreement is not physical identity or a false-positive rate.'}
    inputs = [observations,sources,tracks,reference_observations,reference_sources,reference_tracks]
    return {'summary':summary, 'membership':full,
            'input_sha256':{str(Path(p).resolve()):m.digest(Path(p)) for p in inputs},
            'settings':settings,
            'settings_sha256':hashlib.sha256(json.dumps(settings,sort_keys=True,allow_nan=False).encode()).hexdigest(),
            'evaluator_sha256':m.digest(Path(__file__)),
            'membership_sha256':m.digest(Path(m.__file__))}
