"""Isolated deployed TrackingInput contract check; no inference or IQ access."""
import hashlib
import json
from pathlib import Path
import sys

from pydantic import TypeAdapter
import leo.contracts.scanner_tracking as contracts

path = Path(sys.argv[1])
raw = path.read_bytes()
assert 'sha256:'+hashlib.sha256(raw).hexdigest() == sys.argv[2]
source = TypeAdapter(contracts.TrackingInput).validate_json(
    json.dumps(json.loads(raw)['source']), strict=True)
module = Path(contracts.__file__)
print(json.dumps(dict(typed_TrackingInput_valid=True, session_id=source.session_id,
    probe_count=len(source.probes), contract_sha256=sys.argv[2],
    public_contract_module=dict(path=str(module),sha256='sha256:'+hashlib.sha256(module.read_bytes()).hexdigest()))))
