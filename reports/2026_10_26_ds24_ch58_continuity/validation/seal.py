"""Verify immutable receipts and emit an explicit compact publication allowlist."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ALLOWLIST=(
    'PROTOCOL.md','STATUS.md','FINDINGS.md','baseline.py','adapter.py','audit.py',
    'supplemental.py','report.py','seal.py','test_adapter.py','test_baseline.py',
    'test_scientific_audits.py','test_results.json','source_receipt.json',
    'baseline_audit.json','revisit_audit.json','frequency_audit.json','supplemental_audit.json',
    'qualification.json','candidate_manifest.json','summary.json','validation_summary.png',
    'validation_summary.pdf','DS24-0010_receipt.json','DS24-0011_receipt.json',
    'DS24-0012_receipt.json','DS24-0013_receipt.json')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    initial=read(HERE/'source_receipt.json')
    for path,digest in initial['files_sha256'].items():
        assert sha(path)==digest,path
    for name in ('revisit_audit.json','frequency_audit.json','supplemental_audit.json'):
        for path,digest in read(HERE/name)['source_hashes'].items():
            assert sha(path)==digest,path
    assert read(HERE/'test_results.json')['passed']==33
    assert not read(HERE/'candidate_manifest.json')['ready_for_position']
    files={name:dict(sha256=sha(HERE/name),bytes=(HERE/name).stat().st_size) for name in ALLOWLIST}
    local={f'DS24-{i:04d}_baseline.json':dict(sha256=sha(HERE/f'DS24-{i:04d}_baseline.json'),
        bytes=(HERE/f'DS24-{i:04d}_baseline.json').stat().st_size) for i in range(10,14)}
    summary=read(HERE/'summary.json')
    for name,receipt in local.items():
        assert summary['local_only_large_packets'][name]==receipt['sha256']
    out=dict(schema='ch58-validation-publication-manifest-v1',
        decision='do_not_advance',owned_directory=str(HERE),
        publication_allowlist=files,publication_bytes=sum(v['bytes'] for v in files.values()),
        local_only_baseline_packets=local,local_only_bytes=sum(v['bytes'] for v in local.values()),
        source_input_hashes_unchanged=len(initial['files_sha256']),
        tests_passed=33,regional_position_run_performed=False,
        no_production_edits=True,no_git_mutations=True,no_new_RF=True,no_QNAP_writes=True,
        include_this_manifest=True,
        copy_policy='Copy only allowlisted relative files plus this manifest. Do not recursively copy validation/.')
    with (HERE/'publication_manifest.json').open('x') as stream:
        json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(status='sealed',files=len(files),publication_bytes=out['publication_bytes'],
        local_only_bytes=out['local_only_bytes'],decision=out['decision'])))


if __name__=='__main__':
    main()
