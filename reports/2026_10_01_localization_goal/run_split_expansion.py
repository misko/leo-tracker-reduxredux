"""Cold localization using tracks reconstructed without checking visits."""
# ruff: noqa: E402, I001
import run_fast_pipeline as runner
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from adapter import TrackPort
from physics import TrackObservations

HERE = Path(__file__).resolve().parent
original_prepare = runner.prepare


def prepare(unit):
    scan, height, _ = original_prepare(unit)
    path = HERE/'source-split-expansion-v1'/(unit+'.json')
    assert runner.digest(path) == path.with_suffix('.sha256').read_text().strip()
    source = json.loads(path.read_text())
    observation_path = Path(next(p for p in scan.inputs if p.endswith('observations.json')))
    assert source['observation_sha256'] == runner.digest(observation_path)
    checking = set(map(tuple, source['checking_visits']))
    used, tracks = set(), []
    for t in sorted(source['training_tracks'],
                    key=lambda t: (t['times_s'][-1], t['times_s'][0], t['track_id'])):
        assert all((t['channel'], v) not in checking for v in t['visits'])
        ids = tuple(f"{source['session_id']}:rx{t['receiver_id']}:channel{t['channel']}:visit{v}"
                    for v in t['visits'])
        if used.intersection(ids) or len(ids) < 3:
            continue
        used.update(ids)
        tracks.append((t['track_id'], TrackObservations(
            ids, np.asarray(t['times_s']), np.asarray(t['measured_hz']),
            np.full(len(ids), t['receiver_id'], dtype=int), t['rf_hz'])))
    scan = replace(scan, tracks=tracks, inputs={**scan.inputs, str(path): runner.digest(path)})
    ports = [TrackPort(t, scan.bank, scan.layout, scan.config, height) for _, t in tracks]
    return scan, height, ports


if __name__ == '__main__':
    runner.prepare = prepare
    runner.main()
