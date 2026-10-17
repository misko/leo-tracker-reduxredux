"""Plot the frozen problem-window baseline; no inferred recovery or position truth."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
dataset=json.loads((ROOT/'dataset.json').read_text())
sources={s['source_id']:s for s in json.loads((ROOT/'sources.json').read_text())}
regions=dataset['regions'];y=np.arange(len(regions))
values=np.array([r['original_unassociated_count']/r['observation_count'] for r in regions])
fig,ax=plt.subplots(figsize=(12,8),layout='constrained')
colors=['#0072b2' if sources[r['source_id']]['recording_id'].endswith('upper') else '#009e73' for r in regions]
ax.barh(y,values,color=colors)
labels=[f"{r['region_id']} · {r['source_id']} · RX{r['receiver']} CH{r['channel']} · {r['start_s']:g}–{r['end_s']:g} s" for r in regions]
ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(0,1.16)
for i,r in enumerate(regions):ax.text(values[i]+.01,i,f"{r['original_unassociated_count']}/{r['observation_count']}",va='center',fontsize=9)
ax.set_xticks([0,.25,.5,.75,1],['0%','25%','50%','75%','100%'])
ax.set_xlabel('Originally unassociated fraction · all observations in each requested window')
ax.set_title('DSX01 v1 · 15 inspected windows from 5 recordings\n597/693 originally unassociated · selected problem cases, not overall scanner performance')
ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color='#0072b2',label='Upper-edge recording'),Patch(color='#009e73',label='Lower-edge recording')],loc='lower right')
fig.savefig(ROOT/'baseline-unassociated.png',dpi=150);plt.close(fig)
