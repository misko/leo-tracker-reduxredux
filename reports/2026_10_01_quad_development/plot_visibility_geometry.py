import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

path=Path(__file__).resolve().parent/'visibility-geometry-check-v1.json'
assert digest(path)==path.with_suffix('.sha256').read_text().strip()
data=json.loads(path.read_text());output=path.with_suffix('.png');assert not output.exists()
fig,ax=plt.subplots(figsize=(9,4),constrained_layout=True)
for offset,coordinate,label in [(-.25,'east_km','East (degrees/km)'),(0,'north_km','North (degrees/km)'),(.25,'clock_s','Clock (degrees/s)')]:
    values=[max(c['max_error'] for c in r['checks'] if c['coordinate']==coordinate) for r in data['rows']]
    ax.bar(np.arange(len(values))+offset,values,width=.24,label=label)
ax.set_yscale('log');ax.set_xticks(range(len(data['rows'])),[r['unit'] for r in data['rows']])
ax.set_ylabel('Maximum absolute derivative discrepancy');ax.legend();ax.grid(axis='y',alpha=.2)
ax.set_title('Elevation geometry: all candidates in four fixed tracks\nMaximum over two independent finite-difference steps; no fit')
fig.savefig(output,dpi=160)
