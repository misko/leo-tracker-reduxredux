#!/usr/bin/env python3
"""Require native gate candidates to equal the recorded replay transformation."""
import hashlib,json
from pathlib import Path
import replay

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]
def verify(label,threshold):
    recorded=rows(HERE/'host704-instrumented'/'rows.jsonl')
    native_path=HERE/f'host704-gate-{label}'/'rows.jsonl';native=rows(native_path)
    assert len(recorded)==len(native)==704;mismatches=skipped=0
    for original,result in zip(recorded,native):
        assert original['context']==result['context']
        for old,new in zip(original['rows'],result['rows']):
            assert (old['receiver_id'],old['probe_index'])==(new['receiver_id'],new['probe_index'])
            assert len(old['candidates'])==len(new['candidates'])==8
            for candidate,actual in zip(old['candidates'],new['candidates']):
                expected,was_skipped=replay.gated_candidate(candidate,threshold);skipped+=was_skipped
                expected={key:value for key,value in expected.items() if key in actual}
                mismatches+=expected!=actual
    audit=json.loads((HERE/f'host704-gate-{label}'/'standard-audit.json').read_text())
    replay_result=json.loads((HERE/'replay-results.json').read_text())
    expected_hits=next(r['quality']['totals']['recovered_positive_hits'] for r in replay_result['results'] if r['threshold']==threshold)
    assert not mismatches and audit['totals']['recovered_positive_hits']==expected_hits
    return {'threshold':threshold,'native_rows_sha256':sha(native_path),'candidate_entries':123904,'replay_skipped_candidates':skipped,'candidate_mismatches':mismatches,'recovered_standard_hits':expected_hits}
if __name__=='__main__':
    result={'instrumented_rows_sha256':sha(HERE/'host704-instrumented'/'rows.jsonl'),'variants':[verify('025',.025),verify('100',.1)]}
    (HERE/'native-replay-comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
