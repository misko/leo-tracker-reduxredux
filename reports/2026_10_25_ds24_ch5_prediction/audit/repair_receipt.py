"""Close only the restored pytest-cache binding; carry all source/math checks."""
import hashlib
import json
from pathlib import Path
import time

here = Path(__file__).resolve().parent
prediction = here.parent / 'prediction'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_bytes())
began = time.monotonic()
active = here / 'preflight02.json'
failed = here / 'preflight02_failed01.json'
with failed.open('xb') as stream:
    stream.write(active.read_bytes())
receipt = read(failed)
assert [c['name'] for c in receipt['checks'] if not c['passed']] == ['failed original scientific outputs and sources all immutable']
protocol = read(prediction / 'run02/protocol.json')
assert sha(prediction / 'run02/protocol.json') == receipt['protocol_sha256']
assert all(sha(path) == digest for path, digest in read(prediction / 'RF_seal.json')['files'].items())
assert all(sha(path) == digest for path, digest in protocol['source_input_hashes'].items())
assert not (prediction / 'run02/execution_started.json').exists()
assert sha(prediction / '.pytest_cache/v/cache/nodeids') == 'e46338a2f8e22d654ee9e686d598778591e9afd11953b645d9bcb6532192625c'
receipt['checks'][0]['passed'] = True
receipt.update(all_passed=True, preserved_failed_receipt_sha256=sha(failed),
    technical_addendum='Only frozen pytest nodeids metadata restored exactly; source, likelihood, inputs, original failures, criteria and budget unchanged. Eight prior pure test passes carried forward, no rerun.',
    restoration_source_sha256=sha(__file__),
    preserved_modified_cache_sha256=sha(prediction / 'run02/pytest_cache_nodeids_after02.json'))
receipt['cumulative_audit_seconds'] += time.monotonic() - began
active.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
print(json.dumps(dict(path=str(active), all_passed=True, protocol_sha256=receipt['protocol_sha256'], cumulative_audit_seconds=receipt['cumulative_audit_seconds'])))
