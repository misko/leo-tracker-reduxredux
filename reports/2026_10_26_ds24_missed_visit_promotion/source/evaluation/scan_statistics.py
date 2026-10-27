"""Frozen scan-level promotion metrics; failures stay in intended denominators."""
import math
import numpy as np

ARMS=('c0','fitted_c')


def quantile(values,q):
    """Linear (n-1) quantile, with explicit conservative unavailable ranks."""
    if not values:return math.inf
    ordered=sorted(values);at=(len(ordered)-1)*q;low=math.floor(at);high=math.ceil(at)
    if not math.isfinite(ordered[low]) or not math.isfinite(ordered[high]):return math.inf
    return ordered[low]+(ordered[high]-ordered[low])*(at-low)


def finite(value):return float(value) if math.isfinite(value) else None


def record_lookup(rows,cases):
    allowed=set(cases);lookup={}
    for row in rows:
        if row['case'] not in allowed:raise ValueError('outside frozen cohort: '+row['case'])
        key=(row['case'],row['variant'],row['arm'])
        if key in lookup:raise ValueError('duplicate scan/variant/c-arm record')
        value=row.get('error_m')
        if row.get('valid') and (value is None or not math.isfinite(value) or value<0):
            raise ValueError('valid result requires finite nonnegative error')
        lookup[key]=row
    return lookup


def distribution(values):
    return dict(intended_scans=len(values),finite_scans=sum(math.isfinite(v) for v in values),
        median_m=finite(quantile(values,.5)),p90_m=finite(quantile(values,.9)),
        median_finite=math.isfinite(quantile(values,.5)),p90_finite=math.isfinite(quantile(values,.9)),
        unavailable_rank='positive infinity; not a measured position error')


def compare(rows,cases,variant):
    lookup=record_lookup(rows,cases);out={}
    for arm in ARMS:
        baseline=[];changed=[];paired=[];scans=[];regressions=[]
        for case in cases:
            b=lookup.get((case,'baseline',arm),dict(case=case,status='missing',valid=False))
            t=lookup.get((case,variant,arm),dict(case=case,status='missing',valid=False))
            bv=bool(b.get('valid'));tv=bool(t.get('valid'))
            be=b['error_m'] if bv else math.inf;te=t['error_m'] if tv else math.inf
            baseline.append(be);changed.append(te)
            if bv and not tv:regressions.append(case)
            if bv and tv:paired.append((case,be,te))
            scans.append(dict(case=case,baseline_status=b['status'],treatment_status=t['status'],
                baseline_error_m=finite(be),treatment_error_m=finite(te),
                paired_change_m=te-be if bv and tv else None,
                paired_relative_change=te/be-1 if bv and tv and be>0 else None,
                eligible_lane=t.get('eligible_lane'),baseline_equivalent=t.get('baseline_equivalent',False)))
        bm,tm=quantile(baseline,.5),quantile(changed,.5);bp,tp=quantile(baseline,.9),quantile(changed,.9)
        effect=1-tm/bm if math.isfinite(bm) and bm>0 and math.isfinite(tm) else None
        # Algebraically equivalent to >=10%, avoiding cancellation at exactly90/100.
        median_pass=effect is not None and tm<=.90*bm
        p90_pass=math.isfinite(bp) and math.isfinite(tp) and tp<=bp
        bc=sum(math.isfinite(v) for v in baseline);tc=sum(math.isfinite(v) for v in changed)
        coverage_pass=tc>=bc and not regressions
        pb=[b for _,b,_ in paired];pt=[t for _,_,t in paired]
        complete_effect=1-quantile(pt,.5)/quantile(pb,.5) if paired and quantile(pb,.5)>0 else None
        paired_percent=[(t/b-1) for _,b,t in paired if b>0]
        out[arm]=dict(baseline=distribution(baseline),treatment=distribution(changed),
            cohort_median_improvement=effect,p90_change_m=tp-bp if math.isfinite(tp) and math.isfinite(bp) else None,
            gates=dict(median_at_least_10_percent=median_pass,p90_no_increase=p90_pass,coverage_no_regression=coverage_pass),
            gate_pass=median_pass and p90_pass and coverage_pass,
            baseline_complete=bc,treatment_complete=tc,baseline_valid_to_treatment_invalid=regressions,
            complete_cases=dict(n=len(paired),case_ids=[c for c,_,_ in paired],
                baseline_median_m=finite(quantile(pb,.5)),treatment_median_m=finite(quantile(pt,.5)),
                cohort_median_improvement=complete_effect,
                median_paired_relative_change=finite(quantile(paired_percent,.5)),
                baseline_p90_m=finite(quantile(pb,.9)),treatment_p90_m=finite(quantile(pt,.9)),
                wins=sum(t<b for _,b,t in paired),ties=sum(t==b for _,b,t in paired),losses=sum(t>b for _,b,t in paired)),
            scans=scans)
    return dict(variant=variant,arms=out,both_c_arms_pass=all(out[a]['gate_pass'] for a in ARMS),
        all_intended_scans_retained=len(cases),primary_estimand='one minus ratio of cohort medians; separate from median of paired percentages')


def _vector_quantile(values,q):
    ordered=np.sort(values,axis=1);at=(ordered.shape[1]-1)*q;lo=math.floor(at);hi=math.ceil(at)
    a,b=ordered[:,lo],ordered[:,hi];out=np.full(len(a),np.inf);ok=np.isfinite(a)&np.isfinite(b)
    out[ok]=a[ok]+(b[ok]-a[ok])*(at-lo)
    return out


def bootstrap(rows,cases,variants,replicates=10000,seed=20261026):
    lookup=record_lookup(rows,cases);indices=np.random.default_rng(seed).integers(0,len(cases),size=(replicates,len(cases)));out={}
    def values(variant,arm):
        return np.asarray([lookup.get((c,variant,arm),{}).get('error_m') if lookup.get((c,variant,arm),{}).get('valid') else np.inf for c in cases],float)
    def interval(data):
        good=data[np.isfinite(data)]
        return dict(finite_replicates=len(good),finite_fraction=len(good)/replicates,
            percentile95=([float(v) for v in np.quantile(good,[.025,.975],method='linear')] if len(good) else None))
    for variant in variants:
        out[variant]={}
        for arm in ARMS:
            b=values('baseline',arm)[indices];t=values(variant,arm)[indices]
            bm,tm=_vector_quantile(b,.5),_vector_quantile(t,.5);bp,tp=_vector_quantile(b,.9),_vector_quantile(t,.9)
            effect=np.full(replicates,np.nan);good=np.isfinite(bm)&np.isfinite(tm)&(bm>0);effect[good]=1-tm[good]/bm[good]
            p90=np.full(replicates,np.nan);good=np.isfinite(bp)&np.isfinite(tp);p90[good]=tp[good]-bp[good]
            out[variant][arm]=dict(cohort_median_improvement=interval(effect),p90_change_m=interval(p90))
    return dict(unit='paired scan',replicates=replicates,seed=seed,same_draws_across_variants_and_arms=True,
        intervals_conditioned_on_finite_replicates=True,not_a_new_promotion_gate=True,results=out)
