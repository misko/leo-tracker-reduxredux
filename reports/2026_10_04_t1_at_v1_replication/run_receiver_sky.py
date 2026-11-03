"""Bounded read-only collection, user-owned artifacts; independent parallel scans."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
OUT = HERE / 'receiver-sky-maps'
RELEASE = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
SCANS = ['A', 'B'] + [f'N{i:02d}' for i in range(1, 17)]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def one(scan):
    folder = OUT / 'evidence'; folder.mkdir(parents=True, exist_ok=True)
    probe = folder / f'{scan}-probes.json'
    export_hash=digest(HERE/'export_receiver_sky_probes.py')
    if not probe.exists() or json.loads(probe.read_text()).get('exporter_sha256')!=export_hash:
        call = subprocess.run(['sudo', '-n', RELEASE, str(HERE/'export_receiver_sky_probes.py'), scan],
                              capture_output=True, text=True, timeout=120, check=True)
        value = json.loads(call.stdout)
        value['exporter_sha256']=export_hash
        probe.write_text(json.dumps(value))
    target = OUT / 'paired' / f'{scan}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    collector_hash=digest(HERE/'collect_receiver_sky.py')
    if target.exists() and json.loads(target.read_text()).get('collector_sha256')==collector_hash:
        result = json.loads(target.read_text())
        assert result['sources'][str(probe)]=='sha256:'+digest(probe)
    else:
        try:
            call = subprocess.run(['sudo', '-n', sys.executable, str(HERE/'collect_receiver_sky.py'), scan, str(probe)],
                                  capture_output=True, text=True, timeout=120, check=True,
                                  env={'PATH': '/usr/bin:/bin', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'})
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f'{scan}: {exc.stderr}') from exc
        result = json.loads(call.stdout)
        result['collector_sha256']=collector_hash
        target.write_text(json.dumps(result))
    print(scan, 'candidates', result['candidate_count'], result['counts'], flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--scans', nargs='+', default=SCANS); p.add_argument('--workers', type=int, default=4)
    args=p.parse_args()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in as_completed([pool.submit(one, scan) for scan in args.scans]): result.result()
