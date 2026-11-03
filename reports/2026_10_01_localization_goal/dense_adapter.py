"""Change fitting resolution only; acquisition and raw evidence stay fixed."""
from dataclasses import replace

from acquisition_dot import prepare  # Establish verified research import paths.
from adapter import TrackPort


def dense_ports(scan, height, max_points):
    config = replace(scan.config, max_points=max_points)
    return [TrackPort(track, scan.bank, scan.layout, config, height)
            for _, track in scan.tracks]


__all__ = ['dense_ports', 'prepare']
