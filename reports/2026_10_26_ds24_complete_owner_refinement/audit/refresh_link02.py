"""Bind one verified publication-link correction; no numerical audit rerun."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'audit'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
original=AUDIT/'final_seal.json'
old_bytes=original.read_bytes()
assert hashlib.sha256(old_bytes).hexdigest()=='f1317ef617d86a6eb3b7ec03c1605ee85ae5cd4eb6a958e82148062416bcee2a'
old=json.loads(old_bytes)
changed=[p for p,h in old['files'].items() if sha(p)!=h]
assert changed==[str(ROOT/'README.md')]
previous=ROOT.parent/'ds24-complete-owner-refinement-publication-attempt01/README.md'
assert sha(previous)==old['files'][str(ROOT/'README.md')]
before='../../tools/ds23_frozen_precision.py'
after='../2026_10_24_ds24_receiver_shift_witness/source/repository/tools/ds23_frozen_precision.py'
assert previous.read_text().count(before)==1
assert previous.read_text().replace(before,after)==(ROOT/'README.md').read_text()
publisher=ROOT.parent/'publish-ds23-family-cavity-sparse-20261022'
published='reports/2026_10_24_ds24_receiver_shift_witness/source/repository/tools/ds23_frozen_precision.py'
content=subprocess.run(['git','show','HEAD:'+published],cwd=publisher,capture_output=True,check=True).stdout
helper_sha=hashlib.sha256(content).hexdigest()
assert helper_sha=='e93217f0268ec1aabb121ae964778806f2f7ab440714421d7602453175549139'
assert sha('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_frozen_precision.py')==helper_sha
archive=AUDIT/'final_seal01.json'
with archive.open('xb') as f:f.write(old_bytes)
assert sha(archive)==hashlib.sha256(old_bytes).hexdigest()
revision=dict(all_passed=True,scope='One README publication-link correction; no prose or scientific change.',
    prior_final_seal_sha256=sha(archive),previous_README_sha256=sha(previous),
    corrected_README_sha256=sha(ROOT/'README.md'),old_link=before,new_link=after,
    published_and_local_helper_sha256=helper_sha,all_other_previous_bindings_exact=True,
    scientific_reruns=0,numerical_audit_reruns=0)
receipt=AUDIT/'link_revision02.json'
with receipt.open('x') as f:json.dump(revision,f,indent=2);f.write('\n')
updated=dict(old)
updated['files']=dict(old['files'])
updated['files'][str(ROOT/'README.md')]=sha(ROOT/'README.md')
for p in (archive,receipt,Path(__file__)):
    updated['files'][str(p)]=sha(p)
updated.update(revision=2,prior_final_seal_sha256=sha(archive),
    publication_link_only_revision=True,numerical_audits_rerun=False)
for p,h in updated['files'].items():assert sha(p)==h,p
original.write_text(json.dumps(updated,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(all_passed=True,final_seal_sha256=sha(original),
    passed_receipts=updated['passed_receipts'],files=len(updated['files']),revision=2)))
