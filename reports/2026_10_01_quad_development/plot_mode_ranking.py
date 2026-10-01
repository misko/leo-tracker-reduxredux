"""Plot offline selection headroom; reference oracle is not an estimator."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_shared_visibility_pilot import HERE,sealed


def main():
    result=sealed(HERE/'mode-ranking-diagnostic-v1.json')['results'];fig,axes=plt.subplots(1,2,figsize=(10,4))
    x=np.arange(2)
    for shift,key,label in [(-.25,'baseline','Continued baseline'),(0,'objective_choice','Lower objective, offline'),(.25,'geographic_oracle','Reference oracle (unusable)')]:
        for ax,metric in zip(axes,['median_m','p90_m'],strict=True):
            ax.bar(x+shift,[result[k][key][metric] for k in ['pairs','quads']],.25,label=label)
    for ax,title in zip(axes,['Median error','90th percentile error'],strict=True):
        ax.set_xticks(x,['Pairs (32)','Quads (16)']);ax.set_ylabel(title+' (m)');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Existing-mode selection headroom; combined compute budget not validated')
    fig.tight_layout();fig.savefig(HERE/'mode-ranking-diagnostic-v1.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
