"""RF-only saved-output report; no propagation, fitting, or geographic truth."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'rf_report'
ARMS=('c0','fitted_c')
METHODS=('no_addition','hard','mixture')
read=lambda path:json.loads(Path(path).read_bytes())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    seal=read(HERE/'RF_seal.json')
    for name,digest in seal['files'].items():
        if sha(name)!=digest:
            raise ValueError('scientific file changed: '+name)
    OUT.mkdir(exist_ok=False)
    execution=read(HERE/'execution.json')
    rows=[]
    for arm in ARMS:
        for method in METHODS:
            result=next(row for row in execution['all6_slots'] if row['arm']==arm and row['method']==method)
            folder=HERE/arm/method
            raw=read(folder/'raw_endpoint.json') if (folder/'raw_endpoint.json').exists() else {}
            gates=read(folder/'gates.json') if (folder/'gates.json').exists() else {}
            numerical=read(folder/'numerical_qualification.json') if (folder/'numerical_qualification.json').exists() else {}
            source=gates.get('source',{});target=source.get('original_target_gate',{})
            conditional=target.get('conditional_residual_gate',{})
            point=raw.get('endpoint_east_north_km')
            prediction=raw.get('target_prediction') or {}
            control=gates.get('original_reference_reproduction')
            rows.append(dict(arm=arm,method=method,status=result['status'],raw_endpoint_available=bool(raw),
                east_km=point[0] if point else None,north_km=point[1] if point else None,
                complete_refresh_rounds=len(raw.get('history',[])),
                parent_negative_twice_ELBO=raw.get('parent_negative_twice_elbo'),
                target_conditional_negative_twice_log_density=prediction.get('objective'),
                parent_frequency_RMS_hz=gates.get('parent_summary',{}).get('RMS_hz'),
                original_target_profile_RMS_hz=target.get('profile_rms_hz'),
                original_target_profile_bias_hz=target.get('profile_bias_hz'),
                original_target_conditional_RMS_hz=conditional.get('rms_hz'),
                original_target_conditional_mean_hz=conditional.get('mean_hz'),
                original_target_gate_pass=target.get('compatible'),
                original_growth_supported=source.get('original_growth_supported'),
                parent_original_valid=gates.get('parent_original_valid'),
                Gamma_converged=gates.get('Gamma_converged'),final_phase_change_s=gates.get('final_phase_change_s'),
                original_accepted_IDs_lost=len(gates['original_accepted_IDs_lost']) if 'original_accepted_IDs_lost' in gates else None,
                point_numerically_stable=numerical.get('passed'),
                no_addition_reference_reproduced=control.get('passed') if control else None,
                actual_position_accuracy_evaluated=False,source_association_qualified=False,
                operational_policy='exact_original_reference'))
    with (OUT/'outcomes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (OUT/'summary.json').open('x') as stream:
        json.dump(dict(rows=rows,execution=execution,RF_only=True,new_scientific_evaluations=0),stream,indent=2);stream.write('\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    colors={'no_addition':'#333333','hard':'#b34c32','mixture':'#00796b'}
    for ax,arm in zip(axes,ARMS,strict=True):
        control=next(row for row in rows if row['arm']==arm and row['method']=='no_addition')
        x0=np.array([control['east_km'],control['north_km']]) if control['raw_endpoint_available'] else None
        for row in (row for row in rows if row['arm']==arm):
            if row['raw_endpoint_available'] and x0 is not None:
                point=1000*(np.array([row['east_km'],row['north_km']])-x0)
                ax.scatter(*point,s=70,color=colors[row['method']],label=row['method'])
                ax.annotate(row['method'],point,xytext=(5,5),textcoords='offset points',fontsize=8)
            else:
                ax.text(.02,.95-METHODS.index(row['method'])*.08,row['method']+': no final endpoint',transform=ax.transAxes,fontsize=8,va='top')
        ax.axhline(0,color='gray',lw=.6);ax.axvline(0,color='gray',lw=.6);ax.grid(alpha=.2)
        ax.set_title('DS24-0011 · '+('c=0' if arm=='c0' else 'fitted c'))
        ax.set_xlabel('East offset from matched no-addition endpoint (m)')
        ax.set_ylabel('North offset from matched no-addition endpoint (m)')
        ax.set_aspect('equal',adjustable='datalim')
    fig.suptitle('Raw endpoint differences in RF coordinates\nUnqualified source; no geographic accuracy or adoption claim.',fontsize=11)
    fig.savefig(OUT/'RF_endpoint_offsets.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax,arm in zip(axes,ARMS,strict=True):
        these=[row for row in rows if row['arm']==arm]
        for shift,key,label,color in [(-.2,'original_target_profile_RMS_hz','Original profile RMS','#00796b'),
            (0.,'original_target_conditional_RMS_hz','Original conditional RMS','#b34c32'),
            (.2,'original_target_conditional_mean_hz','Absolute conditional mean','#65758b')]:
            valid=[(i,row) for i,row in enumerate(these) if row[key] is not None]
            ax.bar([i+shift for i,row in valid],[abs(row[key]) for i,row in valid],width=.2,label=label,color=color)
        ax.set_xticks(range(3),METHODS);ax.set_ylabel('Hz');ax.grid(axis='y',alpha=.2)
        ax.set_title('c=0' if arm=='c0' else 'fitted c');ax.legend(fontsize=8)
    fig.suptitle('Whole source under unchanged frozen-parent gate predictions\nLow profiled scatter alone does not remove conditional mean/structure or owner-support failures.',fontsize=11)
    fig.savefig(OUT/'source_gate_scales.png',dpi=180);plt.close(fig)
    bindings={str(path):sha(path) for path in OUT.iterdir() if path.is_file()}
    bindings[str(Path(__file__))]=sha(__file__);bindings[str(HERE/'RF_seal.json')]=sha(HERE/'RF_seal.json')
    with (OUT/'seal.json').open('x') as stream:json.dump(dict(files=bindings,RF_only=True),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(final_endpoints=sum(row['raw_endpoint_available'] for row in rows),slots=len(rows))))


if __name__=='__main__':main()
