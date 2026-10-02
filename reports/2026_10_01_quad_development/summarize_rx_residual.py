"""Summarize common/differential energies without treating groups as independent."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok
HERE=Path(__file__).resolve().parent


def main():
    inputs={};rows=[];fig,axes=plt.subplots(1,3,figsize=(12,3.8))
    for ax,unit in zip(axes,UNITS):
        root=HERE/'rx-residual-v1'/unit
        def read(name):
            p=root/name;d=sealed(p);inputs[str(p)]=digest(p);return d
        result=read('result.json');launch=read('launch.json');assert process_ok(launch)
        sources=read('sources.json');verify_sources(sources['source_sha256']);verify_sources(sources['inputs'])
        groups=result['groups'];a=[r['differential_energy'] for r in groups];b=[r['common_energy'] for r in groups]
        ax.scatter(a,b,s=35);lo=min(a+b)/2;hi=max(a+b)*2
        ax.plot([lo,hi],[lo,hi],color='grey',linestyle='--');ax.set_xscale('log');ax.set_yscale('log')
        ax.set_xlabel('Differential energy');ax.set_ylabel('Common energy');ax.grid(alpha=.2)
        ax.set_title(unit.split('-')[0]+f"  pooled ratio {result['pooled_ratio']:.2f}")
        largest=max(groups,key=lambda r:r['common_energy']+r['differential_energy'])
        rows.append(dict(unit=unit,groups=len(groups),dimension=result['dimension'],counts=result['counts'],
            common_energy=result['common_energy'],differential_energy=result['differential_energy'],pooled_ratio=result['pooled_ratio'],
            common_dominant_groups=result['common_dominant_groups'],exploratory_gate=result['exploratory_gate'],
            largest_group_norad=largest['norad'],largest_common_fraction=largest['common_energy']/result['common_energy'],
            largest_differential_fraction=largest['differential_energy']/result['differential_energy'],seconds=launch['elapsed_seconds']))
    fig.suptitle('Matched receiver residuals: each point is one offset-free track pair')
    fig.tight_layout();fig.savefig(HERE/'rx-residual-summary-v1.png',dpi=160);plt.close(fig)
    save(HERE/'rx-residual-summary-v1.json',dict(rows=rows,all_dataset_gate=all(r['exploratory_gate'] for r in rows),inputs=inputs,
        sources={str(Path(__file__).resolve()):digest(__file__)},qualification='In-sample conditional diagnostic, not independent validation or causal attribution.'))
    print(rows)


if __name__=='__main__':main()
