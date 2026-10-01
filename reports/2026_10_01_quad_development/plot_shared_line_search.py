"""Plot the sealed fixed-state line-search diagnosis."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_shared_visibility_pilot import HERE,sealed


def main():
    result=sealed(HERE/'shared-line-search-diagnostic-v1.json');rows=result['rows']
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    a=[r['alpha'] for r in rows]
    for key,label in [('actual_delta','Full objective subtraction'),('termwise_delta','Sum of per-track differences'),('linear_prediction','Gradient prediction')]:
        axes[0].plot(a,[r[key] for r in rows],'.-',label=label)
    axes[0].set_xscale('log');axes[0].set_yscale('symlog',linthresh=1e-11)
    axes[0].axhline(0,color='black',lw=.7);axes[0].set_xlabel('Line-search step multiplier')
    axes[0].set_ylabel('Objective change (negative is improvement)');axes[0].legend(fontsize=8)
    checks=result['direction_checks']
    axes[1].plot([r['step'] for r in checks],[r['numeric'] for r in checks],'.-',label='Central difference')
    axes[1].axhline(checks[0]['analytic'],color='orange',label='Analytic directional derivative')
    axes[1].set_xscale('log');axes[1].set_xlabel('Normalized direction perturbation')
    axes[1].set_ylabel('Directional derivative');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('DS11 failed line search: fixed-state diagnostic, no refit')
    fig.tight_layout();fig.savefig(HERE/'shared-line-search-diagnostic-v1.png',dpi=160)


if __name__=='__main__':main()
