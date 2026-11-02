"""Seal the predeclared RF-only reducer before retrospective geography."""
import hashlib
import json
from pathlib import Path
import time

from decision import decide

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    for path, expected in protocol['source_sha256'].items():
        assert sha(Path(path)) == expected, path
    plan = json.loads((ROOT / 'predictive/plan.json').read_text())
    result = json.loads((ROOT / 'predictive/results.json').read_text())
    assert result['protocol_sha256'] == sha(ROOT / 'protocol.json')
    assert result['plan_sha256'] == sha(ROOT / 'predictive/plan.json')
    rows = result['rows']
    output = dict(created_utc_ns=time.time_ns(),
                  protocol_sha256=sha(ROOT / 'protocol.json'),
                  results_sha256=sha(ROOT / 'predictive/results.json'),
                  reducer_sha256=sha(ROOT / 'decision.py'),
                  geography_read=False,
                  cases={p['case']: decide(p['partitions'],
                      [r for r in rows if r['case'] == p['case']])
                      for p in plan['cases']})
    destination = ROOT / 'decisions.json'
    if destination.exists():
        raise RuntimeError('Decision seal already exists; do not overwrite')
    destination.write_text(json.dumps(output, indent=2) + '\n')
    (ROOT / 'decisions.sha256').write_text(sha(destination) + '  decisions.json\n')
    for case, decision in output['cases'].items():
        print(case, decision['verdict'], decision['qualified_partitions'])


if __name__ == '__main__':
    main()
