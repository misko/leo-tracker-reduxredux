"""Rebuild the existing likelihood on a nested observation subset."""
from dataclasses import replace
import window_inputs
from adapter import TrackPort
from physics import TrackObservations, _spread_indices
from nested_track_sampling import nested_indices


def build_ports(scan, height, limit):
    if limit < scan.config.max_points:
        raise ValueError('Cannot remove baseline evidence')
    config = replace(scan.config, max_points=limit)
    ports, selection = [], []
    for track_id, track in scan.tracks:
        base = _spread_indices(track.times_s, scan.config.max_points)
        indices = nested_indices(track.times_s, base, limit)
        subset = TrackObservations(tuple(track.observation_ids[i] for i in indices),
            track.times_s[indices], track.frequencies_hz[indices],
            track.receiver_indices[indices], track.rf_hz)
        port = TrackPort(subset, scan.bank, scan.layout, config, height)
        if port.observation_ids != subset.observation_ids:
            raise ValueError('Likelihood unexpectedly changed the selected evidence')
        ports.append(port)
        selection.append(dict(track_id=track_id, baseline_indices=base.tolist(),
                              indices=indices.tolist(), observation_ids=list(port.observation_ids)))
    ids = [i for p in ports for i in p.observation_ids]
    if len(ids) != len(set(ids)):
        raise ValueError('Physical observation reused across tracks')
    return ports, selection
