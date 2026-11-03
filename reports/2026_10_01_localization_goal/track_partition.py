"""Reference-blind, conservative alternative partition for a bounded pilot."""


def select_tracks(tracks, points):
    """Greedily prioritize total detector margin, retaining visit exclusivity.

    Margin is a ranking heuristic, not a calibrated probability. The original
    visit-level exclusion remains stricter than candidate identity exclusivity.
    """
    scores = {t['track_id']: sum(p['margin'] for p in points[t['track_id']]) for t in tracks}
    ordered = sorted(tracks, key=lambda t: (-scores[t['track_id']], t['track_id']))
    consumed, selected = set(), []
    for track in ordered:
        keys = {(track['receiver_id'], track['channel'], v) for v in track['visits']}
        if len(track['times_s']) >= 3 and not keys & consumed:
            selected.append(track)
            consumed.update(keys)
    return sorted(selected, key=lambda t: (t['times_s'][-1], t['times_s'][0], t['track_id']))
