"""Freeze published adaptive fits through read-only public reader ports.

No IQ access, refitting, RF collection, or service changes. Run with the deployed
regional worker on PYTHONPATH and its API virtualenv interpreter.
"""

import datetime as dt
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.regional_position import RegionalPositionStore
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


HERE = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo')
# Freeze the eight-hour window at the time this request was first inspected.
END = dt.datetime.fromisoformat('2026-10-07T05:04:02+00:00')
START = END - dt.timedelta(hours=8)


def main():
    captures = []
    recordings = AdaptiveHopIqStore(ROOT, read_only=True)
    positions = RegionalPositionStore(ROOT)
    try:
        inventory = [(ns, sid) for ns, sid in recordings.history_index()
                     if START.timestamp() <= ns / 1e9 < END.timestamp()]
        for ns, sid in sorted(inventory):
            row = dict(session_id=sid, capture_start_utc=dt.datetime.fromtimestamp(ns / 1e9, dt.UTC).isoformat(),
                       capture_start_s=ns / 1e9)
            try:
                recording = recordings.inspect(sid)
                manifest = recording.manifest
                row['recording_manifest_sha256'] = recording.manifest_sha256
                row['timing'] = manifest.timing.model_dump(mode='json') if manifest.timing else None
                row['terminal'] = manifest.receipt.terminal.model_dump(mode='json')
                if not manifest.timing:
                    row['regional_status'] = 'no-capture-timing'
                    captures.append(row)
                    continue
                assert manifest.timing.first_sample_estimate_utc_ns == ns
                status = positions.status(sid)
                row['regional_status'] = status.state
                if status.manifest:
                    doc = status.manifest.document.model_dump(mode='json')
                    assert doc['input_manifest_sha256'] == recording.manifest_sha256
                    row['regional_document_sha256'] = status.manifest.document_sha256
                    row['regional_document'] = doc
                    prefix = canonical_digest(doc['configuration']['run'])
                    cp = RegionalCheckpointStore(ROOT, sid, doc['diagnostics']['checkpoint_binding'])
                    row['selected_calibrations'] = {}
                    basins = {arm['selected']['source_basin'] for method in doc['methods']
                              for arm in method['arms'] if arm['selected']}
                    for basin in sorted(basins):
                        key = prefix + ':' + basin + ':calibration'
                        value = cp.get(key)
                        if not value or not value.get('result'):
                            row['selected_calibrations'][basin] = dict(error='calibration unavailable')
                            continue
                        calibration = value['result']
                        row['selected_calibrations'][basin] = dict(
                            checkpoint_key=key, checkpoint_value_sha256=canonical_digest(value),
                            postfit=calibration['postfit'],
                            correction_nodes_s=calibration['correction']['nodes_s'],
                            correction_knots_hz=calibration['correction']['knots_hz'])
            except Exception as error:
                row['collection_error'] = f'{type(error).__name__}: {error}'
            captures.append(row)
            print(sid, row.get('regional_status'), row.get('collection_error', ''), flush=True)
    finally:
        recordings.close()
    result = dict(snapshot_utc=dt.datetime.now(dt.UTC).isoformat(),
                  capture_window_utc=[START.isoformat(), END.isoformat()],
                  window_basis='capture first-sample time; start inclusive, end exclusive',
                  captures=captures)
    destination = HERE / 'snapshot.json'
    with destination.open('x') as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(f'Wrote {len(captures)} captures to {destination}', flush=True)


if __name__ == '__main__':
    main()
