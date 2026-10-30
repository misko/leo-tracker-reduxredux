"""Record original native predictive noise and curved calibration weights."""
import argparse,copy
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from ds23_predictive_linear import linear_geometry


def stats(values):
    v=np.asarray(values,float)
    return dict(count=len(v),minimum=float(v.min()),median=float(np.median(v)),maximum=float(v.max()))


def run(args):
    rows=[]
    for directory in args.diagnostics:
        pr=read(directory/'protocol.json');inv=read(Path(pr['inventory']));d=context(inv);target=pr['target']
        source=validated_native_source(Path(pr['validation']));d,_=native_context(d,inv,source,target['component'].split('-NATIVE-')[-1])
        for arm,(original,x) in d['problems'].items():
            p=copy.copy(original);p.scan=d['scan'];_,_,sigma,_,_=linear_geometry(p,[target]);c=original.calculate(x)
            groups=p.noise_groups[p.keep];weights=np.asarray(d['powers'])[groups];precision=c['noise_precision'][groups]
            noise=p.point_noise[p.keep];effective=noise/np.sqrt(weights*precision)
            same=np.isin(p.flat_labels[p.keep],[p.labels.index(target['candidate_index'])])
            downweighted=[]
            for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                active=p.keep[sl]
                if not active.any() or d['powers'][k]>=1:continue
                t=p.scan.tracks[i]
                downweighted.append(dict(component=t['key'],norad=row['candidate_norad'],same_family=row['candidate_index']==target['candidate_index'],
                    receiver=t['receiver'],channel=t['channel'],points=int(active.sum()),power=float(d['powers'][k]),
                    conditional_RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][sl][active]**2)))))
            rows.append(dict(scan=inv['job']['label'],arm=arm,source_protocol=pr,
                native_base_sigma_hz=stats(sigma),native_predictive_sigma_hz=stats(sigma*np.sqrt(2)),
                validation_predictive_sigma_hz=float(150*np.sqrt(2)),
                native_weight_reduction_with_fixed150=float(np.median((150/sigma)**2)),
                curved_point_noise_hz=stats(noise),curved_curve_powers=stats(weights),
                curved_Gamma_precisions=stats(precision),curved_effective_sigma_hz=stats(effective),
                same_family_curved_effective_sigma_hz=stats(effective[same]),
                downweighted_curves=downweighted,
                fixed_window_noise_BIC_gain=float(d['scan'].fixed_window_noise['extra_parameter_BIC_gain']),
                receiver_coefficients_not_changed=True,GPS_used=False,future_TLE=False))
    write(args.output,dict(rows=rows,diagnostic_only=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostics',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
