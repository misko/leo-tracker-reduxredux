from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent;r=json.loads((root/'results.json').read_text())['801'];info=json.loads((root/'information.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(11,4.6));delay=np.array(r['delay_us']);mass=np.array(r['scores']['shared_delay']['delay_posterior']);width=np.full(len(delay),delay[1]-delay[0]);width[[0,-1]]/=2
axes[0].plot(delay,mass/width,label='Training-conditioned delay posterior');axes[0].axhline(1/20,color='gray',linestyle='--',label='Uniform scenario prior');axes[0].set(xlabel='Hypothetical differential response delay (µs)',ylabel='Probability density per µs',title='Delay is uncertain and model-dependent');axes[0].legend(fontsize=8)
names=['known_response','independent_pair_offsets','shared_delay'];values=[100*info['models'][name]['trace_fraction_of_known_response'] for name in names]
axes[1].bar(['Known response','Separate pair offsets','Shared delay'],values,color=['gray','orange','steelblue']);axes[1].set(ylabel='Retained local information trace (%)',title='Conditional geometry sensitivity; not accuracy',ylim=(0,110));axes[1].tick_params(axis='x',labelrotation=12)
for i,v in enumerate(values):axes[1].text(i,v+2,f'{v:.1f}%',ha='center')
fig.tight_layout();fig.savefig(root/'shared-response.png',dpi=160)
