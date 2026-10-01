"""Wait for the identified current queue, verify its audits, then run final blocks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = ['DS10-B03','DS11-B03','DS9-B04','DS10-B04']
REMAINING = ['DS11-B04','DS9-B05','DS10-B05','DS11-B05','DS9-B06']


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--wait-pid',type=int,required=True)
    args = parser.parse_args()
    try:
        descriptor = os.pidfd_open(args.wait_pid)
    except ProcessLookupError:
        descriptor = None
    if descriptor is not None:
        try:
            command = (Path('/proc')/str(args.wait_pid)/'cmdline').read_bytes().split(b'\0')
            decoded = [part.decode() for part in command if part]
            assert any(Path(part).name == 'queue_prepared_blocks.py' for part in decoded)
            assert decoded[-4:] == PREVIOUS, 'unexpected process; refuse to wait on unrelated work'
            print(json.dumps(dict(stage='waiting_for_verified_queue',pid=args.wait_pid)),flush=True)
            poller = select.poll(); poller.register(descriptor,select.POLLIN)
            while not poller.poll(30000):
                pass
        finally:
            os.close(descriptor)
    for block in PREVIOUS:
        path = HERE/'independent-v2'/block/'evaluation.json'
        assert 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest() == path.with_suffix('.sha256').read_text().strip()
        rows = json.loads(path.read_text())['rows']
        assert len(rows) == 7 and all(r['block_id'] == block for r in rows)
    print(json.dumps(dict(stage='previous_queue_audits_verified',next_blocks=REMAINING)),flush=True)
    subprocess.run([sys.executable,str(HERE/'queue_prepared_blocks.py'),*REMAINING],check=True)


if __name__ == '__main__': main()
