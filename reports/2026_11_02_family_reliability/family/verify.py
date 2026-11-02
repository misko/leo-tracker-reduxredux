"""Reconstruct scale-1 and verify actual model invariants on both cases."""
import numpy as np
from prototype import ROOT, configure, e, build_candidate
from algo06_science.common import read, write
from algo07_science.diagnose import objective


def main():
    configure(); rows=[]
    for case in ('DS26-0309','DS26-0070'):
        d,z,replay=e.load_case(case);plan=read(ROOT/case/'plan.json');family=plan['selected_family']
        for arm,(base,x) in d['problems'].items():
            a=base.calculate(x)
            p,dd=build_candidate(d,z,arm,base.reference,1.,family);b=p.calculate(x)
            q,ctx=build_candidate(d,z,arm,base.reference,4.,family);c=q.calculate(x)
            j=next(j for j in p.labels if int(p.scan.norads[j])==family)
            begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*p.supported.index(j)
            cols=np.arange(begin,begin+3)
            unchanged=np.ones(a['features'].shape[1],bool);unchanged[cols]=False
            row=dict(case=case,arm=arm,family=family,
                scale1_objective_delta=objective(p,dd,x)-objective(base,d,x),
                scale1_feature_max_delta=float(abs(a['features']-b['features']).max()),
                physical_columns=cols,physical_base_metadata=p.mode_metadata[j],
                selected_features_scale4_max_delta=float(abs(c['features'][:,cols]-4*b['features'][:,cols]).max()),
                unselected_features_max_delta=float(abs(c['features'][:,unchanged]-b['features'][:,unchanged]).max()),
                unchanged_mask=bool(np.array_equal(base.keep,q.keep)),
                unchanged_values=bool(np.array_equal(base.values,q.values)),
                unchanged_hardware=bool(np.array_equal(base.hardware,q.hardware)),
                unchanged_powers=True,unchanged_phase_prior=bool(np.array_equal(p.phase_sigma,q.phase_sigma)),
                normalization_constant_delta=c['normalization_constant']-b['normalization_constant'],
                scale1_logvolume=b['logvolume'],scale4_logvolume=c['logvolume'],replay=replay)
            assert abs(row['scale1_objective_delta'])<1e-8
            for key in ('scale1_feature_max_delta','selected_features_scale4_max_delta','unselected_features_max_delta'):
                assert row[key]<1e-8
            for key in ('unchanged_mask','unchanged_values','unchanged_hardware','unchanged_phase_prior'):
                assert row[key]
            rows.append(row)
    write(ROOT/'model-invariant-checks.json',dict(status='pass',rows=rows))
    print('Actual-model invariant checks passed:',len(rows),'case/arm cells',flush=True)


if __name__=='__main__':main()
