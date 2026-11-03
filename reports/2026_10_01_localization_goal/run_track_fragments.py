"""Fresh acquisition and original fit with unused-visit fragments appended."""
# ruff: noqa: E402, I001
import run_fast_pipeline as runner
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from adapter import TrackPort
from physics import TrackObservations
from track_fragments import append_fragments

HERE = Path(__file__).resolve().parent
original_prepare = runner.prepare


def prepare(unit):
    scan, height, _ = original_prepare(unit)
    provenance_path = HERE/'signal-provenance-v1.json'
    expected = provenance_path.with_suffix('.sha256').read_text().strip()
    assert runner.digest(provenance_path) == expected
    source = next(r for r in json.loads(provenance_path.read_text())['rows'] if r['unit'] == unit)
    assert source['status'] == 'bound'
    path = Path(next(p for p in scan.inputs if p.endswith('observations.json')))
    assert runner.digest(path) == source['observation_sha256']
    document = json.loads(path.read_text())
    selected = append_fragments(document['tracks'])
    tracks = []
    for t in selected:
        ids = tuple(f"{document['session_id']}:rx{t['receiver_id']}:channel{t['channel']}:visit{v}"
                    for v in t['visits'])
        tracks.append((t['track_id'], TrackObservations(
            ids, np.asarray(t['times_s']), np.asarray(t['measured_hz']),
            np.full(len(ids), t['receiver_id'], dtype=int), t['rf_hz'])))
    assert len({v for _, t in tracks for v in t.observation_ids}) == sum(
        len(t.observation_ids) for _, t in tracks)
    scan = replace(scan, tracks=tracks,
                   inputs={**scan.inputs, str(provenance_path): runner.digest(provenance_path)})
    ports = [TrackPort(t, scan.bank, scan.layout, scan.config, height) for _, t in tracks]
    return scan, height, ports


if __name__ == '__main__':
    runner.prepare = prepare
    runner.main()
