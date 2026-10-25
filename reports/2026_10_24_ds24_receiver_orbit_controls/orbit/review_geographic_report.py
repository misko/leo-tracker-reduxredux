"""Independent evaluation-only check of the sealed parent geographic report.

No model fitting, qualification, endpoint choice or parameter tuning occurs.
Spherical vector angles and elementary order statistics independently check
the parent's haversine/NumPy implementation.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
TRUTH=(37.849061591561885,-122.48574968092912)
MODELS=('receiver_specific_noise','receiver_fast_rx1_rf50','receiver_fast_rx1_hz50')
ARMS=('c0','fitted_c')


def read(path):
    return json.loads(path.read_text())


def geographic_distance(latlon):
    def unit(point):
        latitude,longitude=map(math.radians,point)
        return (math.cos(latitude)*math.cos(longitude),math.cos(latitude)*math.sin(longitude),math.sin(latitude))
    a,b=unit(latlon),unit(TRUTH)
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return 6371*math.atan2(math.sqrt(sum(v*v for v in cross)),sum(x*y for x,y in zip(a,b)))


def quantile(values,p):
    ordered=sorted(values);index=(len(ordered)-1)*p;left=math.floor(index);right=math.ceil(index)
    return ordered[left]+(index-left)*(ordered[right]-ordered[left])


def main():
    seal=read(ROOT/'evaluation/batch_seal.json')
    assert seal['passed'] and seal['total_arm_results']==144
    cases=read(ROOT/'noise/protocol.json')['cases'];assert len(cases)==len(set(cases))==24
    report_positions=list(csv.DictReader((ROOT/'report/positions.csv').open()))
    report_summary=list(csv.DictReader((ROOT/'report/summary.csv').open()))
    report_adoption=list(csv.DictReader((ROOT/'report/adoption.csv').open()))
    lookup={(r['case'],r['model'],r['arm'],r['variant']):r for r in report_positions}
    assert len(lookup)==len(report_positions)==336
    endpoints=[];independent=[];counts=[];bindings={};max_gap=0.;maximum_map_gap=0.
    baseline_by_case={};predictive_by_case={}
    sealed_hashes={r['path']:r['sha256'] for m in seal['models'] for r in m['results']}
    for model in MODELS:
        records=[]
        for case in cases:
            path=ROOT/'evaluation/models'/model/(case+'.json');raw=read(path)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==sealed_hashes[str(path)]
            assert raw['status']=='complete' and not raw['GPS_used']
            assert raw['adopted']==raw['paired_valid']
            assert raw['policy_source']==('trial' if raw['adopted'] else 'baseline')
            if case in baseline_by_case:
                assert baseline_by_case[case]==raw['baseline']
            else:
                original_path=Path(raw['baseline_path'])
                assert hashlib.sha256(original_path.read_bytes()).hexdigest()==raw['baseline_sha256']
                original_full=read(original_path);original=original_full['policy_arms']
                for arm in ARMS:
                    for coordinate in ('endpoint_east_north_km','endpoint_latlon'):
                        assert raw['baseline'][arm][coordinate]==original[arm][coordinate]
                baseline_by_case[case]=raw['baseline']
                entries=original_full['selected']['entries'] if original_full['accepted'] else original_full['baseline_entries']
                predictive_ids={oid for entry in entries for oid in entry['observation_ids']}
                assert len(predictive_ids)==sum(entry['points'] for entry in entries)
                predictive_by_case[case]=len(predictive_ids)
                for arm in ARMS:
                    for field in ('predictive_points','additional_predictive_points'):
                        if field in raw['baseline'][arm]:
                            assert raw['baseline'][arm][field]==len(predictive_ids)
            records.append(raw)
            for arm in ARMS:
                base,trial=raw['baseline'][arm],raw['arms'][arm]
                for variant,endpoint in [('trial',trial),('policy',trial if raw['adopted'] else base)]:
                    published=lookup[case,model,arm,variant]
                    error=geographic_distance(endpoint['endpoint_latlon'])
                    gap=abs(error-float(published['error_km']));max_gap=max(max_gap,gap)
                    assert gap<1e-8
                    assert abs(float(published['lat'])-endpoint['endpoint_latlon'][0])<1e-12
                    assert abs(float(published['lon'])-endpoint['endpoint_latlon'][1])<1e-12
                    assert published['adopted']==str(raw['adopted'])
                    assert int(published['predictive_points'])==predictive_by_case[case]
                    assert int(published['active_curved_points'])==base['active_points']
                    if not raw['adopted'] and variant=='policy':
                        assert endpoint is base
                        assert abs(float(published['change_km']))<1e-12
                    before=geographic_distance(base['endpoint_latlon'])
                    delta=error-before
                    assert abs(delta-float(published['change_km']))<1e-8
                    x,y=endpoint['endpoint_east_north_km']
                    mapped=(37.906+y/111.,-122.545+x/(111.32*math.cos(math.radians(37.906))))
                    maximum_map_gap=max(maximum_map_gap,max(abs(a-b) for a,b in zip(mapped,endpoint['endpoint_latlon'])))
                    endpoints.append(dict(case=case,model=model,arm=arm,variant=variant,error_km=error,
                        change_km=delta,rejected_raw_trial=variant=='trial' and not raw['paired_valid']))
        counts.append(dict(model=model,adopted=sum(r['adopted'] for r in records),fallback=sum(not r['adopted'] for r in records)))
    for case in cases:
        for arm in ARMS:
            error=geographic_distance(baseline_by_case[case][arm]['endpoint_latlon'])
            assert abs(error-float(lookup[case,'baseline',arm,'policy']['error_km']))<1e-8
            endpoints.append(dict(case=case,model='baseline',arm=arm,variant='policy',error_km=error,change_km=0.,rejected_raw_trial=False))
    max_stat_gap=0.
    for published in report_summary:
        selected=[r for r in endpoints if (r['model'],r['arm'],r['variant'])==(published['model'],published['arm'],published['variant'])]
        assert len(selected)==int(published['n'])==24
        errors=[r['error_km'] for r in selected]
        expected=dict(mean_km=statistics.fmean(errors),median_km=statistics.median(errors),
            p95_km=quantile(errors,.95),max_km=max(errors))
        for name,value in expected.items():
            gap=abs(value-float(published[name]));max_stat_gap=max(max_stat_gap,gap);assert gap<1e-8
        for name,count in [('improved',sum(r['change_km']<-1e-6 for r in selected)),
            ('worsened',sum(r['change_km']>1e-6 for r in selected)),('tied',sum(abs(r['change_km'])<=1e-6 for r in selected))]:
            assert count==int(published[name])
        independent.append(dict(model=published['model'],arm=published['arm'],variant=published['variant'],**expected))
    assert len(independent)==14
    assert maximum_map_gap<1e-10
    metadata=read(ROOT/'report/summary.json')
    assert metadata['cases']==cases
    assert metadata['coverage']['active_curved']==sum(r['c0']['active_points'] for r in baseline_by_case.values())
    assert metadata['coverage']['predictive']==sum(predictive_by_case.values())
    for count in counts:
        row=next(r for r in report_adoption if r['model']==count['model'])
        assert int(row['adopted'])==count['adopted'] and int(row['fallback'])==count['fallback'] and int(row['cases'])==24
    for path in [ROOT/'evaluation/batch_seal.json',ROOT/'report/summary.csv',ROOT/'report/positions.csv',ROOT/'report/adoption.csv']:
        bindings[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    audit=dict(passed=True,cases=24,c_arms=list(ARMS),trial_models=list(MODELS),sealed_trial_arm_results=144,
        published_position_rows=336,summary_rows=14,maximum_geographic_error_difference_km=max_gap,
        maximum_summary_statistic_difference_km=max_stat_gap,maximum_engine_latlon_map_difference_deg=maximum_map_gap,
        raw_invalid_trials_kept_separate_from_exact_baseline_fallbacks=True,
        legacy_predictive_counts_independently_verified_from_source_native_ID_sets=True,
        no_endpoint_excluded_or_selected_using_GPS=True,no_refits_or_tuning=True,
        spherical_radius_km=6371,evaluation_only_GPS=TRUTH,adoption=counts,independent_statistics=independent,sha256=bindings)
    (OUT/'geographic_report_review.json').write_text(json.dumps(audit,indent=2)+'\n')
    lines=['# Independent geographic-report review','',
        f"Passed. All 24 cases, both c arms and all 144 sealed trial endpoints are accounted for. All 336 published position rows and 14 summary rows match independent recomputation from raw endpoint coordinates. Maximum error discrepancy is {max_gap:.3g} km and maximum aggregate-statistic discrepancy is {max_stat_gap:.3g} km. The independent implementation uses spherical vector-angle distance and elementary order statistics rather than the report’s haversine/NumPy functions.",'',
        'Raw rejected trials remain in the trial statistics. The complete policy uses the trial only when the saved paired RF gates pass; every fallback uses its exact original baseline endpoint in both arms. Trial and policy rows remain separate. No raw trial is silently omitted and no geographic outcome selects an endpoint.','',
        '| Model | Adopted pairs | Exact baseline fallbacks |','|---|---:|---:|']
    for row in counts:lines.append(f"| {row['model']} | {row['adopted']} | {row['fallback']} |")
    lines+=['','No model fits, qualifications, priors or selection rules were changed. GPS was used only in this independent evaluation after the batch seal.']
    (OUT/'GEOGRAPHIC_REPORT_REVIEW.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('sha256','independent_statistics')},indent=2))


if __name__=='__main__':main()
