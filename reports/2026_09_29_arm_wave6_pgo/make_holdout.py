#!/usr/bin/env python3
"""Create a deterministic disjoint 32-dwell PGO holdout from frozen ARM152."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'2026_09_29_arm_wave5_final'/'arm152'
TRAIN=ROOT.parent/'2026_09_29_arm_wave5_final'/'arm4-v2'
OUT=ROOT/'heldout32-reference'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]
def key(row):c=row['context'];return c['session_id'],c['visit_index']
source=load(SOURCE/'rows.jsonl');training={key(x) for x in load(TRAIN/'rows.jsonl')}
remaining=[x for x in source if key(x) not in training];assert len(source)==152 and len(training)==4 and len(remaining)==148
indices=[round(i*(len(remaining)-1)/31) for i in range(32)];assert len(set(indices))==32
chosen=[remaining[i] for i in indices]
if OUT.exists():raise SystemExit(f'{OUT} exists')
OUT.mkdir();(OUT/'rows.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in chosen))
source_manifest=json.loads((SOURCE/'manifest.json').read_text());selected_by_key={(x['session_id'],x['visit_index']):x for x in source_manifest['selected']}
selected=[selected_by_key[key(x)] for x in chosen]
manifest={**source_manifest,'selected':selected,'processed_dwells':32,'processed_windows':704,'rows_sha256':sha(OUT/'rows.jsonl'),'method':'evenly spaced 32 of frozen ARM152 after excluding all four arm4-v2 training metadata contexts','source_rows_sha256':sha(SOURCE/'rows.jsonl'),'source_manifest_sha256':sha(SOURCE/'manifest.json'),'training_rows_sha256':sha(TRAIN/'rows.jsonl'),'training_contexts':[list(x) for x in sorted(training)],'selection_remaining_indices':indices}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copy2(SOURCE/'build-receipt.json',OUT/'build-receipt.json')
timing_keys=chosen[0]['rows'][0]['timings_ms'];means={k:sum(r['timings_ms'][k] for d in chosen for r in d['rows'])/704 for k in timing_keys}
summary={'schema':'arm-wave6-pgo-heldout/v1','dwells':32,'windows':704,'candidate_entries':sum(len(r['candidates']) for d in chosen for r in d['rows']),'mean_timings_ms':means,'source_rows_sha256':sha(SOURCE/'rows.jsonl'),'rows_sha256':sha(OUT/'rows.jsonl'),'training_context_overlap':0,'selection_remaining_indices':indices}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
