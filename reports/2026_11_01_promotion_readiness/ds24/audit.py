"""Verify final DS24 source/input freeze, accounting and fallback fidelity."""
import time
from pathlib import Path
from collections import Counter
import evaluate_ds24 as adapter


def main():
    r=adapter.runner;out=adapter.OUT;began=time.monotonic()
    protocol=r.read(adapter.OUTPUT/'protocol.json')
    r.verify_frozen(adapter.INPUT,adapter.OUTPUT,protocol['cases'][0])
    original=r.read(out.parent/'candidate/protocol.json')
    assert protocol['settings']==original['settings']
    assert all(protocol['source_sha256'].get(p)==h for p,h in original['source_sha256'].items())
    roster=r.read(adapter.INPUT/'roster.json')
    assert len(roster['rows'])+len(roster['unavailable'])==34
    assert {row['case'] for row in roster['rows']}==set(protocol['cases'])
    rows=[]
    for case in protocol['cases']:
        result=r.read(adapter.OUTPUT/case/'result.json')
        attempt=r.read(adapter.OUTPUT/case/'attempt.json')
        assert attempt['protocol_sha256']==r.sha(adapter.OUTPUT/'protocol.json')
        assert attempt['limit_s']==1200
        baseline=protocol['baselines'][case]
        if result['selected'] is None:
            assert result['final']==baseline,(case,'fallback changed')
        else:
            # Recompute the frozen RF-only decision from recorded proofs.
            choice=r.select(baseline,result['records'],result['guards'])
            assert choice['selected']==result['selected'] and choice['final']==result['final']
        assert all(result['final'][a]['associated']==baseline[a]['associated'] for a in r.e.ARMS)
        if result['execution_status']=='complete':
            assert result['protocol_sha256']==r.sha(adapter.OUTPUT/'protocol.json')
        rows.append(dict(case=case,status=result['execution_status'],selected=result['selected'],
            exact_fallback=result['final']==baseline if result['selected'] is None else None,
            supervisor_seconds=result.get('supervisor_seconds')))
    r.write(out/'execution-audit.json',dict(audited_utc_ns=time.time_ns(),
        source_files=len(protocol['source_sha256']),input_files=len(protocol['input_sha256']),
        all_hashes_match=True,original_candidate_settings_and_sources_unchanged=True,
        cases=rows,status=dict(Counter(row['status'] for row in rows)),full_roster=34,
        unavailable=roster['unavailable'],production_modified=False,seconds=time.monotonic()-began,
        authority='saved ALGO06 research states; no live public terminal claim'))
    r.write(out/'roster.json',roster)
    print('Verified all source/input hashes and',len(rows),'outcomes',flush=True)


if __name__=='__main__':main()
