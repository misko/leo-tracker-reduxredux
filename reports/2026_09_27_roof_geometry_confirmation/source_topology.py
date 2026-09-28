"""Truth-free source-anchor collision audit and conservative whole-track filter."""
from collections import defaultdict
from dataclasses import replace


def audit(prepared, source_links):
    links = {}
    for row in source_links:
        key = (row['track_id'], row['observation_id'])
        if key in links:
            raise ValueError('duplicate source-link record')
        links[key] = row['candidate_ids']
    uses = defaultdict(list)
    tracks = {t.track_id:t for t in prepared.tracks}
    if len(tracks) != len(prepared.tracks):
        raise ValueError('duplicate track identity')
    for track in prepared.tracks:
        for oid, training in zip(track.observation_ids, track.training_mask, strict=True):
            ids = links.get((track.track_id, oid), ())
            if len(ids) != 1:
                raise ValueError('every source observation must resolve uniquely for topology audit')
            uses[ids[0]].append(dict(track_id=track.track_id, observation_id=oid, training=bool(training)))
    collisions = [dict(source_candidate_id=cid, uses=rows) for cid, rows in sorted(uses.items()) if len(rows)>1]
    removed = sorted({r['track_id'] for collision in collisions for r in collision['uses']})
    removed_set = set(removed)
    counts = dict(input_tracks=len(tracks), retained_tracks=len(tracks)-len(removed),
        input_observations=sum(len(t.observation_ids) for t in prepared.tracks),
        removed_observations=sum(len(tracks[tid].observation_ids) for tid in removed),
        unique_source_anchors=len(uses), colliding_source_anchors=len(collisions),
        cross_split_source_anchors=sum(len({r['training'] for r in c['uses']})>1 for c in collisions))
    retained = tuple(t for t in prepared.tracks if t.track_id not in removed_set)
    if not retained:
        raise ValueError('topology filter removes every track')
    return retained, dict(rule='Exclude every whole track containing a source anchor used more than once; all train and reserve observations audited; no score, signal strength, receiver position, or satellite criteria.',
        removed_track_ids=removed, counts=counts, collisions=collisions,
        unchanged=not removed)


def filter_prepared(prepared, source_links):
    retained, receipt = audit(prepared, source_links)
    return (prepared if receipt['unchanged'] else replace(prepared, tracks=retained)), receipt
