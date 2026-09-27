"""Bounded desktop DS5 screen/confirm experiment; no hardware or archive writes.

Uses the deployment checkout's existing native research bindings, not a new
runtime dependency. Run with this workspace's Python. Each output is exclusive.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys

import numpy as np
import zstandard

DEPLOY = Path('/home/mouse9911/gits/leo-adaptive-position-deploy')
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(DEPLOY), str(DEPLOY / 'src')]
from tools.native_presence import build_dwell_presence
from tools.presence_dwell import NativeDwell, unpack


def read(path):
    return subprocess.run(['sudo', '-n', 'cat', str(path)], check=True,
                          capture_output=True, timeout=15).stdout


def main():
    signal.alarm(180)
    manifest_path = DEPLOY / 'reports/2026_09_26_ds5_since_local_midnight/manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    dataset = json.loads(manifest_bytes)
    sessions = [s for s in dataset['captures'] if s['admission_status'] == 'included']
    protocol = json.loads((DEPLOY / 'config/analysis/arm-presence-native-tone-ci16-v1.json').read_text())
    flags = tuple(protocol['common_flags']) + tuple(
        f'-DLEO_PRESENCE_{k}={v}' for k, v in protocol['variants'][0]['defines'].items())
    library = build_dwell_presence(OUT / 'dwell.so', cflags=flags)
    rows = []
    inventory = []
    for rate in sorted({s['sample_rate_hz'] for s in sessions}):
        group = [s for s in sessions if s['sample_rate_hz'] == rate]
        inventory.append({'rate': rate, 'scans': len(group),
                          'visits': sum(s['complete_visit_count'] for s in group),
                          'active_seconds': sum(s['active_dwell_seconds'] for s in group)})
        if rate not in (2500000, 5000000):
            continue
        session = group[len(group)//2]
        path = Path(session['recording_manifest_path'])
        raw_manifest = read(path)
        assert 'sha256:' + hashlib.sha256(raw_manifest).hexdigest() == session['recording_manifest_file_sha256']
        m = json.loads(raw_manifest)['manifest']
        events = {e['visit_index']: e for e in m['receipt']['events']}
        chunks = m['chunks']
        # Preselected chronological positions, independent of signal scores.
        for index in (0, len(chunks)//3, 2*len(chunks)//3, len(chunks)-1):
            chunk = chunks[index]
            assert chunk['visit_count'] == 1
            compressed = read(path.parent / chunk['relative_path'])
            assert 'sha256:' + hashlib.sha256(compressed).hexdigest() == chunk['compressed_sha256']
            raw = zstandard.ZstdDecompressor().decompress(compressed, max_output_size=chunk['uncompressed_bytes'])
            assert len(raw) == chunk['uncompressed_bytes']
            assert 'sha256:' + hashlib.sha256(raw).hexdigest() == chunk['uncompressed_sha256']
            iq = np.frombuffer(raw, dtype='<i2').reshape(chunk['sample_count'], -1, 2)
            assert len(iq) == rate * 120 // 1000
            event = events[chunk['first_visit_index']]
            for rx in range(iq.shape[1]):
                with NativeDwell(library, rate, event['target']['edge'], 512) as native:
                    values = np.ascontiguousarray(iq[:, rx, :])
                    # Paired warm runs. Alternate order to reduce order bias.
                    native.run(values, maximum=1, seeded=False)
                    native.run(values, maximum=1, seeded=True)
                    for repeat in range(3):
                        for seeded in ((False, True) if repeat % 2 == 0 else (True, False)):
                            result = unpack(native.run(values, maximum=1, seeded=seeded))
                            rows.append({'session': session['session_id'], 'rate': rate,
                                         'visit': event['visit_index'], 'rx': rx,
                                         'edge': event['target']['edge'], 'repeat': repeat,
                                         'seeded': seeded, 'result': result})
    receipt = {'scope': 'desktop native kernel only; not ARM or end-to-end latency',
               'host': platform.uname()._asdict(), 'cpu_count': os.cpu_count(),
               'ds5_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
               'inventory': inventory, 'rows': rows,
               'limitations': ['two scans, four visits per scan; not a recall qualification',
                               '7.5 and 10 MS/s unsupported by this binding',
                               'I/O, setup, capture, queueing and downstream tracking excluded',
                               'research build flags are not an attestation of DS5 deployed binary']}
    with (OUT / 'results.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(inventory))
    for rate in (2500000, 5000000):
        for seeded in (False, True):
            r = [x['result'] for x in rows if x['rate'] == rate and x['seeded'] == seeded]
            print(rate, seeded, 'wall median ms', np.median([x['total_wall_ms'] for x in r]),
                  'screen CPU median ms', np.median([x['rank']['total_cpu_ms'] for x in r]),
                  'confirm CPU median ms', np.median([x['confirmations'][0]['total_cpu_ms'] for x in r]))


if __name__ == '__main__':
    main()
