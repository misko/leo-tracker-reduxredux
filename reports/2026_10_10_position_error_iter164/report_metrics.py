"""Pure post-evaluation coverage/metrics; no file, model or reference ports."""
import math
from collections import Counter

ARMS=('zero-c','fitted-c')
BRANCHES=('native','zero')
COUNTS={'DS16':63,'DS17':51,'DS18':34,'POST18-development':45}
TOLERANCE_KM=1e-9
FREQUENCY=('objective','posterior_rms_hz','signal_windows')


def finite(value, name, *, nonnegative=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Nonfinite or nonnumeric '+name)
    if nonnegative and value<0:raise ValueError('Negative '+name)
    return float(value)


def statistics(values):
    if not values:return None
    ordered=sorted(values);count=len(ordered)
    def percentile(q):
        location=(count-1)*q;low=math.floor(location);high=math.ceil(location)
        return ordered[low]+(ordered[high]-ordered[low])*(location-low)
    return dict(n=count,mean=math.fsum(ordered)/count,median=percentile(.5),
                p95=percentile(.95),worst=ordered[-1])


def endpoint(row,arm,branch):
    if row is None:return None
    return row.get('arms',{}).get(arm,{}).get(branch)


def qualified(value):
    return value is not None and value.get('status')=='selected' and value.get('qualified') is True


def comparison(members,rows,left,right):
    pairs=[];missing=[]
    for member in members:
        row=rows.get(member['label']);a=endpoint(row,*left);b=endpoint(row,*right)
        if not (qualified(a) and qualified(b) and 'error_km' in a and 'error_km' in b):
            missing.append(member['label']);continue
        pairs.append(dict(label=member['label'],left_km=a['error_km'],right_km=b['error_km'],
                          delta_km=b['error_km']-a['error_km']))
    metrics=dict(left=statistics([p['left_km'] for p in pairs]),
                 right=statistics([p['right_km'] for p in pairs]),
                 delta=statistics([p['delta_km'] for p in pairs]))
    regressions=[p for p in pairs if p['delta_km']>TOLERANCE_KM]
    return dict(membership=len(members),paired=len(pairs),missing=len(missing),missing_labels=missing,
        complete=len(pairs)==len(members),full_metrics=metrics if len(pairs)==len(members) else None,
        available_pair_metrics=metrics,available_pair_scope='available matched subset only' if missing else 'full matched membership',
        left=dict(arm=left[0],branch=left[1]),right=dict(arm=right[0],branch=right[1]),
        delta_definition='right minus left; positive position delta is worse',
        equality_tolerance_km=TOLERANCE_KM,
        improvements=sum(p['delta_km'] < -TOLERANCE_KM for p in pairs),
        equal=sum(abs(p['delta_km'])<=TOLERANCE_KM for p in pairs),
        regressions=len(regressions),regression_labels=[p['label'] for p in regressions],
        regressions_over_1km=[p['label'] for p in pairs if p['delta_km']>1.],
        maximum_regression_km=max((p['delta_km'] for p in regressions),default=None),pairs=pairs)


def aggregate(membership, evaluated_rows):
    """Consume129-style evaluated rows with explicit native/zero branch names.

    The caller authenticates frozen protocols and seals all phase receipts before
    evaluation. This function never authorizes reference access or fabricates a
    missing endpoint. Full-cohort metrics require complete matched coverage.
    """
    if (len(membership)!=193 or len({m['label'] for m in membership})!=193
            or Counter(m['dataset'] for m in membership)!=Counter(COUNTS)):
        raise ValueError('Exact193 membership and dataset counts required')
    authority={m['label']:m for m in membership};rows={}
    for row in evaluated_rows:
        label=row['label']
        if label not in authority or label in rows or row['dataset']!=authority[label]['dataset']:
            raise ValueError('Foreign, duplicate or mismatched evaluation row')
        for arm,branches in row.get('arms',{}).items():
            if arm not in ARMS:raise ValueError('Unknown final c arm')
            if any(k not in (*BRANCHES,'delta_km') for k in branches):
                raise ValueError('Unknown branch: explicit native/zero required')
            for branch in BRANCHES:
                value=branches.get(branch)
                if value is None:continue
                if 'error_km' in value:
                    if not qualified(value):raise ValueError('Unqualified endpoint has position evaluation')
                    finite(value['error_km'],'position error',nonnegative=True)
                for name in FREQUENCY:
                    metric=value.get('frequency',{}).get(name)
                    if metric is not None:finite(metric,name,nonnegative=name!='objective')
        rows[label]=row
    coverage=[]
    for member in membership:
        label=member['label'];row=rows.get(label);endpoints={}
        for arm in ARMS:
            for branch in BRANCHES:
                value=endpoint(row,arm,branch)
                endpoints[branch+'/'+arm]=dict(status=(value or {}).get('status','missing-endpoint'),
                    qualified=qualified(value),evaluated=qualified(value) and 'error_km' in value,
                    evaluation_status=(value or {}).get('evaluation_status'),
                    reason=(value or {}).get('reason') or (value or {}).get('error')
                           or (value or {}).get('evaluation_error'))
        coverage.append(dict(label=label,dataset=member['dataset'],row_present=row is not None,
            endpoints=endpoints,statuses={} if row is None else row.get('statuses',{}),
            failure_reasons={} if row is None else row.get('failure_reasons',{})))
    output={}
    for dataset in (*COUNTS,'all193'):
        members=[m for m in membership if dataset=='all193' or m['dataset']==dataset]
        frequency={}
        for branch in BRANCHES:
            frequency[branch]={}
            for arm in ARMS:
                metrics={}
                for name in FREQUENCY:
                    values=[];missing=[]
                    for member in members:
                        value=endpoint(rows.get(member['label']),arm,branch)
                        metric=(value or {}).get('frequency',{}).get(name)
                        if not qualified(value) or metric is None:missing.append(member['label'])
                        else:values.append(float(metric))
                    stats=statistics(values)
                    metrics[name]=dict(membership=len(members),available=len(values),missing_labels=missing,
                        full_metrics=stats if not missing else None,available_endpoint_metrics=stats)
                frequency[branch][arm]=metrics
        output[dataset]=dict(membership=len(members),
            discovery={arm:comparison(members,rows,(arm,'native'),(arm,'zero')) for arm in ARMS},
            c_effect={branch:comparison(members,rows,('zero-c',branch),('fitted-c',branch)) for branch in BRANCHES},
            frequency=frequency)
        for value in output[dataset]['c_effect'].values():
            value['interpretation']='Matched policy c-arm sensitivity; selected stages and realized banks are not asserted identical. Not a controlled same-model likelihood contrast.'
    return dict(membership=193,evaluation_rows=len(rows),missing_row_labels=[m['label'] for m in membership if m['label'] not in rows],
        coverage=coverage,datasets=output,
        frequency_scope='Operational model-specific summaries; banks/stages may differ. No cross-bank objective delta or accuracy inference.',
        position_scope='Single-pass diagnostic; incomplete pairs never supply full-cohort metrics. No deployed-policy parity claim.')
