"""Collect completed fifth-wave measurements with their frozen hit audits."""
import hashlib
import json
from pathlib import Path
import collect_wave3 as collector

collector.METHODS = [
    ('wave4-control', 'arm_wave4_combined', 'host704', ['arm4', 'arm4-repeat']),
    ('wide-block-128', 'arm_conditioned_wide_blocks', 'host704-128', ['arm4-128']),
    ('wide-block-256', 'arm_conditioned_wide_blocks', 'host704-256', ['arm4-256']),
    ('quadratic-block-64', 'arm_conditioned_quadratic', 'host704-b64', ['arm4-b64']),
    ('sample-lane-neon', 'arm_conditioned_sample_neon', 'host704-fused', ['arm4']),
    ('rate-gate-300', 'arm_rate_coarse_gate', 'host704', ['arm4-300']),
    ('rate-gate-312', 'arm_rate_coarse_gate', 'host704-312', ['arm4-312', 'arm4-312-repeat']),
    ('rate-gate-linear-screen', 'arm_wave5_candidate', 'host704', ['arm4']),
    ('rate-gate-quadratic-screen', 'arm_gate_quadratic', 'host704', ['arm4']),
    ('linear-gate-direct-input', 'arm_direct_ci16_ingest', 'host704-v3', ['arm4-v3']),
    ('exact-coarse-peak-selection', 'arm_peak_select_fast', 'host704', ['arm4-v2']),
    ('quadratic-gate-direct-input', 'arm_wave5_combined', 'host704', ['arm4']),
    ('quadratic-gate-sparse-peak-scan', 'arm_sparse_peak_scan', 'host704', ['arm4']),
    ('quadratic-gate-prepared-input', 'arm_direct_ci16_prefix', 'host704', ['arm4']),
    ('quadratic-gate-direct-sparse', 'arm_wave5_sparse_combined', 'host704', ['arm4']),
    ('combined-final', 'arm_wave5_final', 'host704', ['arm4']),
    ('combined-final-v2-argument-guard', 'arm_wave5_final', 'host704-v2', ['arm4-v2']),
]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_receipt(summary, copied_receipt, source_receipt):
    """Validate a cohort receipt against its reproducible source-tree build."""
    copied_hash=sha(copied_receipt)
    assert summary['build_sha256']==copied_hash
    assert sha(source_receipt)==copied_hash
    receipt=json.loads(source_receipt.read_text())
    binary_hash=summary['binary_sha256']
    names=[name for name,digest in receipt['binaries'].items() if digest==binary_hash]
    assert len(names)==1
    binary=source_receipt.parent/names[0]
    assert binary.is_file() and sha(binary)==binary_hash
    for relative,digest in receipt['sources'].items():
        source=source_receipt.parent/relative
        assert source.is_file() and sha(source)==digest
    return {'copied_receipt_sha256':copied_hash,'source_receipt':str(source_receipt),
            'binary':names[0],'binary_sha256':binary_hash,
            'source_files_verified':len(receipt['sources']),
            'source_sha256':receipt['sources']}

def verify_provenance(result):
    """Attach source-tree build verification; published archives are separate."""
    verified=[]
    for method,directory,host,arms in collector.METHODS:
        root=collector.REPORTS/('2026_09_29_'+directory)
        for cohort in [host,*arms]:
            cohort_root=root/cohort
            summary=json.loads((cohort_root/'summary.json').read_text())
            copied=cohort_root/'build-receipt.json'
            matches=[]
            for receipt in root.rglob('build-receipt.json'):
                if receipt==copied or sha(receipt)!=summary['build_sha256']:
                    continue
                payload=json.loads(receipt.read_text())
                if any((receipt.parent/name).is_file() for name in payload.get('binaries',{})):
                    matches.append(receipt)
            assert len(matches)==1, (method,cohort,matches)
            entry=validate_receipt(summary,copied,matches[0])
            entry.update(method=method,cohort=cohort)
            verified.append(entry)
            result['evidence_sha256'][str(copied.relative_to(collector.REPORTS))]=sha(copied)
            result['evidence_sha256'][str(matches[0].relative_to(collector.REPORTS))]=sha(matches[0])
            result['evidence_sha256'][str((matches[0].parent/entry['binary']).relative_to(collector.REPORTS))]=entry['binary_sha256']
    result['source_tree_provenance']=verified
    result['provenance_scope']='source-tree receipts, binaries, and sources verified; publisher archives separately'
    return result

def collect_larger_panel(result):
    root = collector.REPORTS/'2026_09_29_arm_wave5_final'
    folder = root/'arm152'
    manifest_path = folder/'manifest.json'
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('complete'):
        return
    payload = {}
    for name in ['manifest.json', 'summary.json', 'standard-audit.json', 'cpu-distribution.json']:
        path = folder/name
        payload[name] = json.loads(path.read_text())
        result['evidence_sha256'][str(path.relative_to(collector.REPORTS))] = sha(path)
    assert payload['summary.json']['dwells'] == 152
    assert payload['standard-audit.json']['totals']['reference_positive_hits'] == 4573
    assert payload['standard-audit.json']['totals']['windows'] == 3344
    payload['source_tree_provenance'] = validate_receipt(
        payload['summary.json'], folder/'build-receipt.json', root/'builds/arm/build-receipt.json')
    result['larger_arm_panel'] = payload

if __name__ == '__main__':
    result = collector.collect()
    verify_provenance(result)
    collect_larger_panel(result)
    result['qualification'] = (
        'Rate thresholds tuned on this DS7 cohort; separate DS8/DS9 transfer '
        'results in arm_rate_gate_transfer. Lower-order screens approximate '
        'frequency search, not the final FP64 GLRT. All 22 windows retained; '
        'gates emit fewer candidates. ARM timing is four 2.5 MS/s dwells.'
    )
    (collector.HERE/'wave5-results.json').write_text(json.dumps(result, indent=2)+'\n')
