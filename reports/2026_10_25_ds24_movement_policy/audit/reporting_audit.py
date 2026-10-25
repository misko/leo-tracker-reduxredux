"""Independent geographic arithmetic/table reconstruction after scientific seals."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SITE=(37.849061591561885,-122.48574968092912)
CENTER=(37.906,-122.545)


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def csv_rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))


def ll(x):return (CENTER[0]+x[1]/111.,CENTER[1]+x[0]/(111.32*math.cos(math.radians(CENTER[0]))))


def independent_error(x):
    def unit(point):
        lat,lon=map(math.radians,point)
        return (math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat))
    a,b=unit(ll(x)),unit(SITE)
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return 6371*math.atan2(math.sqrt(math.fsum(v*v for v in cross)),math.fsum(u*v for u,v in zip(a,b,strict=True)))


def quantile(values,q):
    values=sorted(values);index=(len(values)-1)*q;i=math.floor(index)
    return values[i]+(index-i)*(values[min(i+1,len(values)-1)]-values[i])


def main():
    assert read(HERE/'movement_artifacts.json')['status']==read(HERE/'recovery_artifacts.json')['status']=='passed'
    evaldir=ROOT/'evaluation'
    summary=read(evaldir/'summary.json')
    assert summary['source_sha256']==sha(evaldir/'report.py')
    for name,digest in summary['geographic_reporting_after_scientific_seals'].items():assert sha(ROOT/name/'scientific_seal.json')==digest
    decisions={r['case']:r for r in read(ROOT/'movement/decisions.json')['cases']}
    bindings=read(ROOT/'movement/full_data_bindings.json')
    maximum=0.;numeric_cells=0
    positions=csv_rows(evaldir/'positions.csv')
    assert len(positions)==204
    for row in positions:
        if row['status']=='input_unavailable':
            assert row['error_km']=='' and row['east_km']==''
            continue
        case,arm=row['case'],row['arm'];full=bindings[case]
        base=read(full['baseline_binding']['path'])['policy_arms'][arm]
        candidate=read(full['candidate_binding']['path'])['arms'][arm]
        adopted=(row['policy']=='existing_RX1' and full['original_adopted']) or (row['policy']=='movement_gate' and decisions[case]['adopted'])
        endpoint=candidate if adopted else base
        x=endpoint['endpoint_east_north_km']
        assert float(row['east_km'])==x[0] and float(row['north_km'])==x[1]
        error=independent_error(x);maximum=max(maximum,abs(error-float(row['error_km'])))
        assert abs(error-float(row['error_km']))<1e-8
        assert float(row['curved_RMS_hz'])==endpoint['RMS_hz']
        assert int(row['likelihood_points'])==int(row['curved_points'])+int(row['predictive_points'])
        assert abs(float(row['likelihood_percent_of_original_GLRT'])-100*int(row['likelihood_points'])/int(row['original_GLRT_points']))<1e-12
        numeric_cells+=9
    summaries=csv_rows(evaldir/'summary.csv');assert len(summaries)==12
    for row in summaries:
        chosen=[r for r in positions if r['status']=='qualified_position' and r['policy']==row['policy'] and r['arm']==row['arm']
            and (row['subset']=='all24_development' or r['case'] not in ('DS24-0017','DS24-0095'))]
        baseline={r['case']:float(r['error_km']) for r in positions if r['status']=='qualified_position' and r['policy']=='baseline' and r['arm']==row['arm']}
        errors=[float(r['error_km']) for r in chosen];changes=[float(r['error_km'])-baseline[r['case']] for r in chosen]
        expected=dict(mean_km=statistics.mean(errors),median_km=statistics.median(errors),P95_km=quantile(errors,.95),worst_km=max(errors),
            mean_change_km=statistics.mean(changes),median_change_km=statistics.median(changes),
            improved=sum(v < -1e-12 for v in changes),worsened=sum(v > 1e-12 for v in changes),unchanged=sum(abs(v)<=1e-12 for v in changes))
        for name,value in expected.items():assert abs(float(row[name])-value)<1e-11;numeric_cells+=1
    recovery=csv_rows(evaldir/'recovery_positions.csv');assert len(recovery)==16
    branch=dict(graph_policy='',support_repair01_strict='repair01',support_active_incumbent_control='eligibility02')
    for row in recovery:
        case,arm=row['case'],row['arm'];parent=read(ROOT/'recovery'/case/'parent.json')
        if row['policy']=='baseline':endpoint=parent['arms'][arm];coverage=parent['coverage'][arm]
        else:
            directory=ROOT/'recovery'/branch[row['policy']]/case
            if row['policy']=='graph_policy':directory=directory/'graph'
            result=read(directory/'result.json');endpoint=result['policy_arms'][arm]
            coverage=result['selected']['coverage'][arm] if result['selected'] else parent['coverage'][arm]
        error=independent_error(endpoint['endpoint_east_north_km']);maximum=max(maximum,abs(error-float(row['error_km'])))
        assert abs(error-float(row['error_km']))<1e-8
        assert float(row['curved_RMS_hz'])==endpoint['RMS_hz']
        for key,source in [('original_GLRT_points','total_GLRT'),('associated_points','associated'),('curved_points','curved_points'),('predictive_points','predictive_points'),('likelihood_points','likelihood_points')]:
            assert int(row[key])==coverage[source];numeric_cells+=1
    native=read(ROOT/'recovery/report_native03/manifest.json');native_points=0
    for rel,digest in native['files'].items():
        path=ROOT/'recovery/report_native03'/rel;assert sha(path)==digest
        if path.suffix!='.csv':continue
        case=path.parent.name
        lookup={r['observation_id']:r for r in read(Path('/srv/bulk/leo/research/ds25-20261024')/case/'observations.json')}
        rows=csv_rows(path)
        for row in rows:
            original=lookup[row['observation_id']]
            assert float(row['plotted_CFO_hz'])==original['measured_cfo_hz']
            assert float(row['native_time_s'])==float(row['track_time_s'])==original['time_s']
        native_points+=len(rows)
    figures=sorted((ROOT/'figures').glob('*.png'))
    for path in figures:
        with Image.open(path) as image:image.verify()
    assert len(figures)==6
    output=dict(status='passed',evaluation_only_GPS=list(SITE),no_position_fits=True,
        source_sha256=sha(Path(__file__)),position_rows=len(positions),summary_rows=len(summaries),recovery_policy_rows=len(recovery),
        numeric_cells_verified=numeric_cells,maximum_independent_geographic_difference_km=maximum,
        distance_method='Independent unit-sphere vectors and atan2(cross norm,dot), compared with producer haversine',
        native_plot_points_verified=native_points,native_plot_max_coordinate_discrepancy=0.,figures_verified=len(figures),
        final_trial_validity_columns_explicit=True,
        final_table_bindings=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in sorted(evaldir.glob('*.csv'))],
        evaluation_source_sha256=sha(evaldir/'report.py'),evaluation_seal_sha256=sha(evaldir/'seal.json'))
    with (HERE/'reporting_audit.json').open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
