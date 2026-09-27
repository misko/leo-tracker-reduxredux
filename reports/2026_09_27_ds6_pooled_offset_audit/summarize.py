import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
r=json.loads((HERE/'results.json').read_text());assert r['complete']
allc=[c for s in r['scans'] for t in s['tracks'] for c in t['candidates']];maps=[t['candidates'][0] for s in r['scans'] for t in s['tracks']]
summary=dict(scans=len(r['scans']),tracks=len(maps),candidates=len(allc),old_nonstationary=sum(abs(c['old_gradient_per_hz'])>1e-7 for c in allc),new_unconverged=sum(not c['converged'] for c in allc),max_new_gradient=max(abs(c['gradient']) for c in allc),fixed_original_map_train_gain=sum(c['new_train']-c['old_train'] for c in maps),fixed_original_map_held_gain=sum(c['held_change'] for c in maps),max_offset_shift_hz=max(abs(c['new_offset_hz']-c['old_offset_hz']) for c in allc),within_top_two_winner_changes=sum(int(np.argmax([c['new_train'] for c in t['candidates']]))!=0 for s in r['scans'] for t in s['tracks']))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
gain=[sum(t['candidates'][0]['new_train']-t['candidates'][0]['old_train'] for t in s['tracks']) for s in r['scans']]
fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
axes[0].bar(range(43),gain);axes[0].set(xlabel='Scan index in frozen DS6 order',ylabel='Training log-score gain',title='Original MAP identities fixed; offsets corrected')
axes[1].hist(np.log10(np.maximum([abs(c['old_gradient_per_hz']) for c in allc],1e-16)),bins=30,label='12-step solver',alpha=.7);axes[1].hist(np.log10(np.maximum([abs(c['gradient']) for c in allc],1e-16)),bins=30,label='Stationary solver',alpha=.7);axes[1].axvline(-7,color='black',ls='--');axes[1].set(xlabel='log10 absolute loss derivative (per Hz)',ylabel='Candidate count',title='Training-offset stationarity');axes[1].legend(fontsize=8);fig.savefig(HERE/'offsets.png',dpi=160)
print(json.dumps(summary,indent=2))
