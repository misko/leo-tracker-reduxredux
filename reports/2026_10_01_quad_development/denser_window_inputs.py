"""Nested evidence ports in the unchanged independent-scan coordinate layout."""
from run_window import prepare_window
from denser_track_ports import build_ports
from leo.analysis.localization_windows import WindowTrackPort


def prepare_denser_window(unit, point_limit):
    if point_limit not in (8, 16):
        raise ValueError('Pilot supports only eight and sixteen points')
    binding, scans, columns, precision, _ = prepare_window(unit)
    ports, selection = [], []
    for (scan, height, _), indices in zip(scans, columns):
        local, selected = build_ports(scan, height, point_limit)
        ports.extend(WindowTrackPort(p, indices, len(precision)) for p in local)
        selection.append(dict(scan=scan.unit_id, tracks=selected))
    return (binding, scans, columns, precision, ports), selection
