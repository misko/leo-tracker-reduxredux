"""Read-only audit of persisted tracking products; never opens IQ or collects RF."""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def collect(root, out):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    products = []
    errors = []
    for folder in sorted(root.glob('scanner-shared-tracking-v*')):
        count = 0
        for path in folder.glob('*/manifest.json'):
            try:
                raw = path.read_bytes()
                doc = json.loads(raw)['document']
                tracks = doc.get('tracklets', [])
                epochs = [t['start_utc_ns'] for t in tracks if t.get('start_utc_ns')]
                if not epochs:
                    continue
                epoch = min(epochs) / 1e9
                if not start.timestamp() <= epoch <= end.timestamp():
                    continue
                products.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                                     observed_epoch=epoch, document=doc))
                count += 1
            except Exception as exc:
                errors.append(dict(path=str(path), error=str(exc)))
        print(folder.name, count, flush=True)
    result = dict(start=start.isoformat(), end=end.isoformat(), products=products, errors=errors)
    out.write_text(json.dumps(result))
    print('total', len(products), 'errors', len(errors), flush=True)


def inventory(root, out, window):
    bounds = json.loads(window.read_text())
    lo, hi = [datetime.fromisoformat(bounds[k]).timestamp() * 1e9 for k in ('start', 'end')]
    rows, errors = [], []
    for path in (root / 'scanner-adaptive-recordings').glob('*/manifest.json'):
        try:
            with path.open('rb') as stream:
                prefix = stream.read(512 * 1024)
                stream.seek(max(0, path.stat().st_size - 128 * 1024))
                suffix = stream.read()
            def field(key, data, numeric=True):
                pattern = rb'"' + key.encode() + rb'"\s*:\s*' + (rb'([0-9.]+)' if numeric else rb'"([^"]+)"')
                found = re.search(pattern, data)
                return found[1].decode() if found else None
            epoch = field('first_sample_estimate_utc_ns', suffix) or field('created_utc_ns', prefix)
            if epoch is None:
                raise ValueError('No bounded timestamp')
            if not lo <= int(epoch) <= hi:
                continue
            # The plan geometry precedes restoration settings; timing repeats the true rate.
            rates = re.findall(rb'"sample_rate_hz"\s*:\s*([0-9]+)', suffix)
            if not rates:
                raise ValueError('No bounded sample rate')
            rows.append(dict(session_id=path.parent.name, captured_ns=int(epoch),
                             sample_rate_hz=int(rates[-1]), radio=field('radio_id', suffix, False),
                             gain_db=field('gain_db', suffix), dwell_ms=field('valid_visit_ms', suffix),
                             path=str(path)))
        except Exception as exc:
            errors.append(dict(path=str(path), error=str(exc)))
    out.write_text(json.dumps(dict(rows=rows, errors=errors)))
    print('inventory', len(rows), 'errors', len(errors), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/srv/bulk/leo'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--inventory-window', type=Path)
    args = parser.parse_args()
    if args.inventory_window:
        inventory(args.root, args.out, args.inventory_window)
    else:
        collect(args.root, args.out)
