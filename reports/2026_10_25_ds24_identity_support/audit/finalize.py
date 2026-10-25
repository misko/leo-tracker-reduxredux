"""Bind final independent receipts; include both terminal passes in the budget."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SCI=HERE.parent/'scientific'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

output=HERE/'final_seal.json'
if output.exists():raise FileExistsError('preserve final independent seal')
preflight=read(HERE/'preflight.json');first=read(HERE/'terminal.json');final=read(HERE/'terminal02.json')
total=preflight['cumulative_audit_seconds']+first['audit_wall_seconds']+final['audit_wall_seconds']
assert final['all_passed'] and total<180
files={str(p):sha(p) for p in sorted(HERE.glob('*')) if p.is_file() and p!=output}
result=dict(all_passed=True,authoritative_terminal=str(HERE/'terminal02.json'),
    protocol_sha256=sha(SCI/'protocol.json'),RF_seal_sha256=sha(SCI/'RF_seal.json'),
    files=files,original_failed_terminal_retained=True,
    reporting_hash_repair='exact original RF reporting bytes restored; no hash exemption or scientific change',
    budget=dict(preflight_including_earlier_numeric_checks=preflight['cumulative_audit_seconds'],
                first_failed_terminal=first['audit_wall_seconds'],
                second_terminal=final['audit_wall_seconds'],cumulative_audit_seconds=total,cap_seconds=180),
    additional_corpus_propagation=0,additional_integrations=0,position_fits=0,geographic_truth_read=False,
    counts=final['counts'])
output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(path=str(output),sha256=sha(output),cumulative_audit_seconds=total)))
