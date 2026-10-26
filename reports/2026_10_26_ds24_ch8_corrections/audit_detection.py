"""Read-only detection-stage CH8 audit; no gate or inference changes."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo/research/ds25-20261024')
AUDIT = Path('/srv/bulk/leo/research/ds24-per-channel-audit-20261026')
sources = {}


def read(path):
    data = path.read_bytes()
    sources[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


summary = read(AUDIT/'summary.json')
data = defaultdict(list)
for case in summary['cases']:
    doc = read(ROOT/case/'tracking.json')['source']
    receiver_ids = sorted({p['receiver_id'] for p in doc['probes']})
    for p in doc['probes']:
        rx = receiver_ids.index(p['receiver_id']) + 1
        candidates = p['candidates']
        for c in candidates:
            assert c['passed_fractional_margin_gate'] == (c['fractional_margin'] >= .025)
        margin = max((c['fractional_margin'] for c in candidates), default=None)
        passes = sum(c['passed_fractional_margin_gate'] for c in candidates)
        for receiver in (0, rx):
            for edge in ('both', p['edge']):
                data[receiver, p['channel'], edge].append((margin, passes))

rows = []
for (rx, ch, edge), entries in sorted(data.items()):
    n = len(entries)
    passed = [v for v, k in entries if k]
    no_candidate = sum(v is None for v, _ in entries)
    near_fail = sum(v is not None and .0125 <= v < .025 for v, _ in entries)
    other_fail = n - no_candidate - near_fail - len(passed)
    if edge == 'both':
        prior = next(r for r in summary['rows'] if r['group'] == 'full' and
                     r['arm'] == 'fitted_c' and r['receiver'] == rx and r['channel'] == ch)
        assert n == prior['processed_windows'] and len(passed) == prior['GLRT']
    rows.append(dict(receiver=rx, channel=ch, edge=edge, windows=n,
                     winners=len(passed), no_exported_candidate=no_candidate,
                     near_fail=near_fail, other_fail=other_fail,
                     winner_percent=100*len(passed)/n,
                     near_fail_percent=100*near_fail/n,
                     median_winning_margin=float(np.median(passed)),
                     multiple_passing_candidates=sum(k > 1 for _, k in entries)))

with (OUT/'detection.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)
(OUT/'summary.json').write_text(json.dumps(dict(cases=summary['cases'], rows=rows,
    near_fail_definition='maximum exported fractional margin in [0.0125, 0.025); diagnostic only',
    caveat='No exported fractional candidate does not prove no acquisition candidate or no signal.',
    source_sha256=sources, matched_original_winners_and_windows=True), indent=2)+'\n')

fig, ax = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
colors = {1:'#8467bd', 2:'#32968f'}
for rx in (1, 2):
    r = [v for v in rows if v['receiver']==rx and v['edge']=='both']
    ch = [v['channel'] for v in r]
    ax[0].plot(ch, [v['winner_percent'] for v in r], 'o-', color=colors[rx], label=f'RX{rx}')
    ax[1].plot(ch, [v['near_fail_percent'] for v in r], 'o-', color=colors[rx], label=f'RX{rx}')
ax[0].set(title='Gate-passing GLRT winners', ylabel='Percentage of processed receiver windows', ylim=(0,50))
ax[1].set(title='Below the margin gate: diagnostic only', ylabel='Windows with maximum margin 0.0125–0.025 (%)', ylim=(0,12))
for a in ax:
    a.set(xlabel='Channel', xticks=range(1,9)); a.grid(alpha=.2); a.legend()
fig.suptitle('DS24: same 24 fast scans; no threshold change')
fig.savefig(OUT/'detection_by_receiver.png', dpi=180)
fig.savefig(OUT/'detection_by_receiver.pdf')
print(json.dumps([r for r in rows if r['edge']=='both' and r['channel'] in (1,8)],indent=2))
