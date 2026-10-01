"""Fixed DS9 numerical-progress snapshot; geographic scoring waits for all cases."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE,sealed


def main():
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for index,(unit,limit) in enumerate([('DS9-B01-D1',180),('DS9-B01-Q',360)]):
        directory=HERE/'marginal-window-pilot-v1'/unit
        receipt=sealed(directory/(unit+'.json'));audit=sealed(directory/'evaluation.json')
        launch=sealed(directory/(unit+'.launch.json'));assert audit['accepted']
        values=receipt['best']['objectives'];label=unit.split('-')[-1]
        axes[0].plot(range(len(values)),[values[0]-v for v in values],'.-',label=label)
        axes[1].bar(index,launch['original_cost_s'],color='C0',label='Historical work' if index==0 else None)
        axes[1].bar(index,launch['incremental_seconds'],bottom=launch['original_cost_s'],color='C1',label='Marginal refinement' if index==0 else None)
        axes[1].scatter([index],[limit],marker='_',color='black',label='Budget' if index==0 else None)
    axes[0].set_xlabel('Accepted steps');axes[0].set_ylabel('Within-model objective reduction');axes[0].legend()
    axes[1].set_xticks([0,1],['DS9 pair','DS9 quad']);axes[1].set_ylabel('Charged inference seconds');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('DS9 marginal pair/quad numerical snapshot; no accuracy claim')
    fig.tight_layout();fig.savefig(HERE/'marginal-window-progress-01.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
