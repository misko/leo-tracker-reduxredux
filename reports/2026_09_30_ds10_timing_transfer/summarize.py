"""Verify complete timing transfer and report all boundary failures."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    result=json.loads((HERE/'results.json').read_text())
    for name,digest in result['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    rows=result['rows']
    assert len(rows)==24 and len({r['session_id'] for r in rows})==24
    for row in rows:
        assert json.loads((HERE/'scans'/f"{row['session_id']}.json").read_text())==row
        candidates=[row['inherited']]+[p for p in row['peaks'] if p['qualified']]
        assert row['selected']['score']==max(p['score'] for p in candidates)
    peaks=[p for row in rows for p in row['peaks']]
    qualified=[p for p in peaks if p['qualified']]
    rejected=[p for p in peaks if not p['qualified']]
    gain=sum(row['training_gain'] for row in rows)
    assert result['training_gain']==gain and result['joint_refit_triggered']==(gain>.01)
    summary=dict(scans=24,peaks=len(peaks),qualified_peaks=len(qualified),rejected_peaks=len(rejected),
                 all_rejected_at_boundary=all(abs(p['tau_s'])>=4.999 for p in rejected),
                 maximum_rejected_training_gain=max(p['score']-r['inherited']['score'] for r in rows for p in r['peaks'] if not p['qualified']),
                 training_gain=gain,held_gain=result['held_gain'],joint_refit_triggered=result['joint_refit_triggered'],
                 maximum_timing_change_s=max(abs(r['selected']['tau_s']-r['inherited']['tau_s']) for r in rows),
                 maximum_qualified_gradient=max(abs(p['gradient']) for p in qualified),
                 maximum_qualified_gradient_audit=max(p['gradient_audit'] for p in qualified),
                 elapsed_seconds=result['elapsed_seconds'])
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
