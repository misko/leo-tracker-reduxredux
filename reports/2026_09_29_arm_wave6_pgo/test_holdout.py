#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;out=HERE/'heldout32-reference';base=HERE.parent/'2026_09_29_arm_wave5_final'
load=lambda p:[json.loads(x) for x in p.read_text().splitlines()]
key=lambda r:(r['context']['session_id'],r['context']['visit_index'])
rows=load(out/'rows.jsonl');source=load(base/'arm152'/'rows.jsonl');training={key(x) for x in load(base/'arm4-v2'/'rows.jsonl')};manifest=json.loads((out/'manifest.json').read_text());summary=json.loads((out/'summary.json').read_text())
assert len(rows)==32 and not ({key(x) for x in rows}&training)
remaining=[x for x in source if key(x) not in training];assert rows==[remaining[i] for i in manifest['selection_remaining_indices']]
assert manifest['rows_sha256']==hashlib.sha256((out/'rows.jsonl').read_bytes()).hexdigest()
assert manifest['processed_windows']==32*22 and summary['windows']==32*22 and summary['training_context_overlap']==0
print('PGO heldout32 reference verified')
