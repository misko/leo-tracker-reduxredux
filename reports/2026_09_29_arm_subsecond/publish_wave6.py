"""Publish completed Wave6 evidence, preserving the original build receipts."""
import sys
from pathlib import Path
import publish_wave5

publish = publish_wave5.publish
publish.EXPERIMENTS += tuple('2026_09_29_arm_wave6_' + name for name in (
    'proposal_rank', 'proposal_fold', 'dwell_input', 'proposal_simd',
    'compiler_matrix', 'combined', 'proposal_resolution', 'pgo',
    'combined_pgo', 'dwell_products', 'proposal_fastmath',
))
original_receipt_sources = publish.receipt_sources
original_excluded = publish.excluded

def excluded(path):
    # This is baseline bookkeeping copied into an edited source workspace,
    # not the receipt for a Wave6 build. The original Wave5 receipt remains
    # published with its original source archive; actual Wave6 receipts are
    # under builds/ and the evaluated cohort directories.
    stale = ('2026_09_29_arm_wave6_proposal_fold', 'sources', 'build-receipt.json')
    return original_excluded(path) or tuple(path.parts[-3:]) == stale

publish.excluded = excluded

def receipt_sources(receipt, data):
    # PGO v1 used this spelling. Adapt only in memory: the archived receipt
    # remains byte-identical and its exact source inventory is still bound.
    if 'sources' not in data and isinstance(data.get('source_tree_sha256'), dict):
        data = dict(data, sources=data['source_tree_sha256'])
    return original_receipt_sources(receipt, data)

publish.receipt_sources = receipt_sources

if __name__ == '__main__':
    publish.main()
    relative = Path('reports/2026_09_29_arm_fine_input_neon/tests')
    for name in ['test_fine_precision_tail_asan.c', 'run_tail_asan.sh', 'tail_asan.stderr']:
        publish.safe_copy(publish.REPORTS.parent/relative/name, Path(sys.argv[1])/relative/name)
    for experiment in ('2026_09_29_arm_wave6_pgo','2026_09_29_arm_wave6_combined_pgo'):
        for source in (publish.REPORTS/experiment).glob('profile-data*.tar.gz'):
            relative=source.relative_to(publish.REPORTS.parent)
            publish.safe_copy(source,Path(sys.argv[1])/relative)
