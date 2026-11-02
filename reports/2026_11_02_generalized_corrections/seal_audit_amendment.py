"""Preserve the unused first seal; amend a reviewer-only prelaunch hash race."""
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (ROOT/'evaluation/execution_started.json').exists()
    assert not list((ROOT/'evaluation/cases').glob('*/result.json'))
    original = ROOT/'protocol.json'
    protocol = json.loads(original.read_text())
    changes = {p:dict(before=h, after=sha(Path(p)))
               for p,h in protocol['source_sha256'].items() if sha(Path(p)) != h}
    assert set(changes) == {str(ROOT/'review/audit_receipts.py')}, changes
    amendment = dict(created_utc_ns=time.time_ns(), original_protocol_sha256=sha(original),
        reason='Postfit reviewer tightened receipt checks during initial seal; launch refused before any workers or fit receipts',
        inference_policy_or_sources_changed=False, numerical_attempts_before_amendment=0,
        source_changes=changes)
    path=ROOT/'prelaunch_amendment.json'
    assert not path.exists()
    path.write_text(json.dumps(amendment,indent=2)+'\n')
    protocol['prelaunch_amendment_sha256']=sha(path)
    for p,change in changes.items():
        protocol['source_sha256'][p]=change['after']
    destination=ROOT/'execution_protocol.json'
    assert not destination.exists()
    destination.write_text(json.dumps(protocol,indent=2)+'\n')
    print('Execution protocol',sha(destination))


if __name__=='__main__':
    main()
