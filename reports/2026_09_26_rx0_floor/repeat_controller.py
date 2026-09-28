"""Temporary bounded coax-repair campaign, run by a transient systemd unit.

Waits for the existing capture, runs at most five additional 300-second captures,
and stops when a finished pilot analysis supports both receivers. Never edits
published captures. The unit's ExecStopPost restores the ordinary capture timer.
"""

import json
import subprocess
import time
from pathlib import Path

import zstandard

HERE = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo')
INITIAL = 'scan-fw-60d9d1e77c14da0a'
DEADLINE = 1790469000  # 2026-09-27 00:30:00 UTC, including initial capture.
CAPTURE_PYTHON = '/home/mouse9911/gits/pluto-plus-utils-feature-103/.venv/bin/python'
CAPTURE_SOURCE = '/opt/leo-v058-adaptive/1e7bebed663bc2178a1b91af5b98eb55bc97dc84/src'


def strong_probe_counts(session):
    manifests = list((ROOT / 'scanner-adaptive-analysis' / session).glob('*/metrics-manifest.v8.json'))
    if not manifests:
        return None
    manifest = manifests[0]
    document = json.loads(manifest.read_bytes())['document']
    counts = [0, 0]
    decoder = zstandard.ZstdDecompressor()
    for entry in document['visits']:
        raw = decoder.decompress((manifest.parent / entry['relative_path']).read_bytes(), max_output_size=entry['uncompressed_bytes'])
        for probe in json.loads(raw)['document']['probes']:
            if any(c['passed_fractional_margin_gate'] and c['fractional_margin'] >= .1 for c in probe['candidates']):
                counts[probe['receiver_id']] += 1
    return counts


def main():
    # The systemd unit runs this controller as root; RF access is always as leo.
    subprocess.run(['systemctl', 'stop', 'leo-v052-adaptive.timer'], check=True)
    while subprocess.check_output(['systemctl', 'show', 'leo-v052-adaptive.service', '-p', 'ActiveState', '--value'], text=True).strip() in ('active', 'activating', 'deactivating'):
        if time.time() >= DEADLINE - 310:
            return
        time.sleep(1)
    sessions = [INITIAL]
    for index in range(1, 6):
        if time.time() >= DEADLINE - 310:
            print('STOP: 30-minute campaign boundary', flush=True)
            return
        if index > 1:
            for session in sessions:
                counts = strong_probe_counts(session)
                print('PILOT', session, counts, flush=True)
                if counts is not None and min(counts) >= 20:
                    print('STOP: both receivers have at least 20 strong pilot probes', flush=True)
                    return
        nonce = f'20260927-coax-{index}-{time.time_ns()}'
        evidence = ROOT / 'v052-adaptive-live' / 'coax-repair-20260927' / nonce
        command = [
            'sudo', '-n', '-u', 'leo', 'env', f'PYTHONPATH={CAPTURE_SOURCE}',
            'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
            'flock', '--wait', '5', '/run/leo-adaptive-pipeline.lock',
            CAPTURE_PYTHON, str(HERE / 'repeat_capture.py'), nonce,
            '--serial', '1040005e0b100007100010000bf33a5d4d',
            '--uri', 'ip:192.168.1.20', '--sample-rate', '2500000',
            '--duration-ms', '300000', '--evidence-root', str(evidence),
            '--iq-spool-root', '/srv/postgres-nvme/leo-scanner-spool/v052-adaptive',
        ]
        print('START', index, nonce, flush=True)
        subprocess.run(command, check=True, timeout=min(390, DEADLINE-time.time()))
        for summary in evidence.glob('*.json'):
            sessions.append(Path(json.loads(summary.read_bytes())['iq_archive']).name)
        print('COMPLETE', sessions[-1], flush=True)
        subprocess.run(['systemctl', 'start', '--no-block', 'leo-adaptive-spool-transfer.service'], check=True)
    print('STOP: capture count limit', flush=True)


if __name__ == '__main__':
    main()
