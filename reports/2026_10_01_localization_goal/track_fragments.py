"""Preserve the baseline partition and salvage source-disjoint track fragments."""
import hashlib
import json


def append_fragments(tracks):
    ordered = sorted(tracks, key=lambda t: (t['times_s'][-1], t['times_s'][0], t['track_id']))
    used, retained, excluded = set(), [], []

    def key(track, i):
        return track['receiver_id'], track['channel'], track['visits'][i]

    for track in ordered:
        ids = {key(track, i) for i in range(len(track['times_s']))}
        if ids & used or len(track['times_s']) < 3:
            excluded.append(track)
        else:
            retained.append(track)
            used.update(ids)
    for track in excluded:
        remaining = [i for i in range(len(track['times_s'])) if key(track, i) not in used]
        segments = []
        for i in remaining:
            if not segments or track['times_s'][i]-track['times_s'][segments[-1][-1]] > 4.:
                segments.append([])
            segments[-1].append(i)
        for indices in segments:
            if len(indices) < 6 or track['times_s'][indices[-1]]-track['times_s'][indices[0]] < 3.:
                continue
            fragment = dict(track)
            for field in ['times_s', 'measured_hz', 'training_mask', 'visits']:
                fragment[field] = [track[field][i] for i in indices]
            identity = json.dumps([track['track_id'], indices], separators=(',', ':'))
            fragment['track_id'] = 'fragment:'+hashlib.sha256(identity.encode()).hexdigest()
            retained.append(fragment)
            used.update(key(track, i) for i in indices)
    return retained
