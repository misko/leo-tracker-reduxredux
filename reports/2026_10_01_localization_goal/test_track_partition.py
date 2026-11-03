from track_partition import select_tracks


def track(name, visits, rx=0):
    return dict(track_id=name, visits=visits, times_s=visits, receiver_id=rx, channel=1)


def test_high_margin_alternative_replaces_early_track_without_double_counting():
    tracks = [track('a', [1, 2, 3]), track('b', [2, 3, 4]), track('c', [2, 3, 4], 1)]
    points = {name: [dict(margin=value)] for name, value in [('a', 1), ('b', 2), ('c', 3)]}
    assert [t['track_id'] for t in select_tracks(tracks, points)] == ['b', 'c']
    assert select_tracks(tracks[::-1], points) == select_tracks(tracks, points)


def test_ties_deterministic_short_tracks_excluded():
    tracks = [track('b', [1, 2, 3]), track('a', [1, 2, 3]), track('c', [5, 6])]
    points = {t['track_id']: [dict(margin=1)] for t in tracks}
    assert [t['track_id'] for t in select_tracks(tracks, points)] == ['a']
