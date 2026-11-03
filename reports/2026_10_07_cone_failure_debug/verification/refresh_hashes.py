"""Refresh provenance checks only; preserve completed numerical audit rows."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
audit=json.loads((HERE/'audit.json').read_text())
for row in audit['receipts']:
    receipt=json.loads((HERE.parent/row['family']/f"{row['case']}.json").read_text())
    row['source_hash_mismatches']=[p for p,h in receipt['source_hashes'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    assert not row['source_hash_mismatches'],row
(HERE/'audit.json').write_text(json.dumps(audit,indent=2))
print('All six receipt source bindings match; numerical audit rows preserved.')
