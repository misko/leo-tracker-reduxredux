"""Run the complete compatible extension; reused runner preserves child limits."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from panel_run import run
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent


def main():
    manifest = read(HERE / 'compatible-inputs.json')
    for row in manifest['eligible']:
        assert digest(row['path']) == row['sha256']
    jobs = [(i, a) for i in (4, 9, 19, 20) for a in ('doppler', 'receiver', 'signed', 'swapped', 'permuted')]
    receipts = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(run, i, a) for i, a in jobs]):
            r = f.result()
            receipts.append(r)
            print(json.dumps({k: r[k] for k in ('index', 'arm', 'exit_code', 'wall_s')}), flush=True)
    with (HERE / 'compatible-run.json').open('x') as f:
        json.dump(dict(receipts=receipts, sources={str(p): digest(p) for p in (Path(__file__), HERE / 'COMPATIBLE_PROTOCOL.md', HERE / 'compatible-inputs.json', HERE / 'panel_run.py')}), f, indent=2)


if __name__ == '__main__':
    main()
