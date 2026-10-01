"""Visualize the sealed, failure-selected boundary diagnostic."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_window_pilot import HERE,BOUNDARY,sealed


def main():
    directory=HERE/'shared-window-pilot-v1'/BOUNDARY
    receipt=sealed(directory/(BOUNDARY+'.json'));audit=sealed(directory/'evaluation.json')
    launch=sealed(directory/(BOUNDARY+'.launch.json'));values=receipt['best']['objectives']
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    axes[0].plot(range(len(values)),[values[0]-v for v in values],'.-')
    axes[0].set_xlabel('Accepted optimizer steps');axes[0].set_ylabel('Objective reduction within new model')
    axes[1].bar(['Targeted pair'],[launch['original_cost_s']],label='Charged historical work')
    axes[1].bar(['Targeted pair'],[launch['incremental_seconds']],bottom=[launch['original_cost_s']],label='New-model refinement')
    axes[1].axhline(180,color='black',ls='--',label='Original pair budget')
    axes[1].set_ylabel('Inference seconds');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle(f'{BOUNDARY}: failure-selected diagnostic, accepted={audit["accepted"]}')
    fig.tight_layout();fig.savefig(HERE/'shared-boundary-diagnostic-v1.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
