import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_wave4_combined/host704'
OUTPUT=HERE/'reference-wave4-2500'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def test_reference_is_exact_order_preserving_source_filter():
    source=[line for line in (SOURCE/'rows.jsonl').read_text().splitlines() if json.loads(line)['context']['rate_hz']==2500000]
    filtered=(OUTPUT/'rows.jsonl').read_text().splitlines();assert filtered==source;assert len(filtered)==152
    manifest=json.loads((OUTPUT/'manifest.json').read_text());bindings=json.loads((OUTPUT/'source-bindings.json').read_text())
    contexts=[json.loads(line)['context'] for line in filtered]
    assert manifest['complete'] and manifest['selected']==contexts
    assert manifest['processed_dwells']==152 and manifest['processed_windows']==3344
    assert manifest['rows_sha256']==sha(OUTPUT/'rows.jsonl')==bindings['filtered_rows_sha256']
    assert bindings['source_rows_sha256']==sha(SOURCE/'rows.jsonl')
    assert bindings['source_manifest_sha256']==sha(SOURCE/'manifest.json')
    assert len({(c['session_id'],c['visit_index']) for c in contexts})==152
