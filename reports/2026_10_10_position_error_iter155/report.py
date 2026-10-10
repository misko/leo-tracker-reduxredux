"""Completion-gated numerical parity/cost report; no production/reference ports."""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ('fitted-c', 'zero-c')


def canonical(value):
    payload=json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
    return 'sha256:'+hashlib.sha256(payload).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def total(values):
    return sum(values) if all(finite(v) and v>=0 for v in values) else None


def summarize(plan, receipts, digest, hashes):
    rows=[]
    for member in plan['members']:
        raw=receipts[member['label']]
        arms={}
        for arm in ARMS:
            value=raw['arms'][arm]; diagnostic=value.get('diagnostic',{})
            calls=[{k:c.get(k) for k in ('label','called','elapsed_s','objective_elapsed_s','error')}
                   for c in diagnostic.get('calls',[])]
            called=[c for c in calls if c['called'] is True]
            derivatives=diagnostic.get('derivatives',[])
            ratios=[abs(d['difference'])/d['tolerance'] for d in derivatives
                    if finite(d.get('difference')) and finite(d.get('tolerance')) and d['tolerance']>0]
            additive=diagnostic.get('additive')
            arms[arm]=dict(status=value['status'],error=value.get('error') or diagnostic.get('error'),
                calls=calls,actual_calls=len(called),attempts=diagnostic.get('joint_attempts'),
                anchor=diagnostic.get('anchor'),derivatives=derivatives,
                gradient_max_tolerance_ratio=max(ratios) if len(ratios)==2 else None,
                additive=additive,additive_tolerance_ratio=(abs(additive['difference'])/additive['tolerance']
                    if additive and finite(additive.get('difference')) and finite(additive.get('tolerance'))
                    and additive['tolerance']>0 else None),
                live_anchor_audit=diagnostic.get('live_anchor_audit'),
                objective_elapsed_s=total([c['objective_elapsed_s'] for c in called]) if calls else None,
                guarded_call_elapsed_s=total([c['elapsed_s'] for c in calls]) if calls else None,
                diagnostic_elapsed_s=diagnostic.get('elapsed_s'),
                reconstruction_elapsed_s=value.get('reconstruction_elapsed_s'),
                seed_stage=value.get('seed_stage'))
        rows.append(dict(label=member['label'],dataset=member['dataset'],status=raw['status'],
                         error=raw.get('error'),matched_model=raw.get('matched_model'),arms=arms,
                         input_reconstruction_elapsed_s=raw.get('input_reconstruction_elapsed_s'),
                         elapsed_s=raw.get('elapsed_s')))
    groups={}
    for dataset in sorted({r['dataset'] for r in rows})+['all12']:
        selected=[r for r in rows if dataset=='all12' or r['dataset']==dataset]
        groups[dataset]=dict(members=len(selected),matched_models=sum(r['matched_model'] is True for r in selected),
            arms={arm:dict(members=len(selected),passed=sum(r['arms'][arm]['status']=='passed' for r in selected),
                failed=sum(r['arms'][arm]['status']!='passed' for r in selected),
                actual_calls=sum(r['arms'][arm]['actual_calls'] for r in selected)) for arm in ARMS})
    return dict(all12_terminal=True,protocol_canonical_digest=digest,rows=rows,coverage=groups,
                artifact_sha256=hashes,scope='Consumed numerical callback parity/cost only; no position or c-effect accuracy claim')


def build(protocol, directory, *, root=ROOT):
    protocol,directory,root=map(Path,(protocol,directory,root))
    plan=json.loads(protocol.read_text());digest=canonical(plan)
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if sha(root/name)!=expected:raise ValueError('frozen artifact changed: '+name)
    for name,expected in plan['runtime']['sha256'].items():
        if sha(name)!=expected:raise ValueError('runtime artifact changed: '+name)
    labels=[m['label'] for m in plan['members']]
    if len(labels)!=12 or len(set(labels))!=12:raise ValueError('exact12 identities required')
    receipts={};hashes={str(protocol):sha(protocol)}
    for label in labels:
        path=directory/(label+'.json');claim=directory/(label+'.claim.json')
        if not path.exists() or not claim.exists():raise ValueError('all12 terminal receipts and claims required')
        row=json.loads(path.read_text());claimed=json.loads(claim.read_text())
        for item in (row,claimed):
            if item.get('label')!=label or item.get('protocol_sha256')!=digest:raise ValueError('foreign receipt/claim')
        if row.get('status') not in ('complete','failed') or set(row.get('arms',{}))!=set(ARMS):
            raise ValueError('all24 arm outcomes required')
        if any(row['arms'][a].get('status') not in ('passed','failed') for a in ARMS):raise ValueError('nonterminal arm')
        if (row['status']=='complete') != all(row['arms'][a]['status']=='passed' for a in ARMS):
            raise ValueError('inconsistent member/arm status')
        for arm in ARMS:
            d=row['arms'][arm].get('diagnostic',{})
            if d and (d.get('status')!=row['arms'][arm]['status'] or d.get('joint_attempts')!=len(d.get('calls',[]))):
                raise ValueError('inconsistent diagnostic status/call count')
            if row['arms'][arm]['status']=='passed' and (d.get('joint_attempts')!=6 or
                    sum(c.get('called') is True for c in d.get('calls',[]))!=6):
                raise ValueError('passed diagnostic must contain six actual calls')
        receipts[label]=row;hashes[str(path)]=sha(path);hashes[str(claim)]=sha(claim)
    summary=summarize(plan,receipts,digest,hashes)
    summary['protocol_file_sha256']=sha(protocol)
    summary['raw_receipt_bytes']=sum((directory/(label+'.json')).stat().st_size for label in labels)
    return summary


def num(value):
    return f'{value:.6g}' if finite(value) else 'unavailable'


def markdown(summary):
    if not summary.get('all12_terminal'):raise ValueError('full terminal report only')
    lines=['# Original B7 conditional-mode parity and cost','',
        'All twelve consumed members and both original final c arms are retained. '
        'This measures numerical callback parity and cost, not position accuracy, integration accuracy or a c-effect.',
        '', '![Callback cost and normalized numerical discrepancies](parity_cost.png)','',
        '| Dataset | Members | Matched models | Fitted passed / failed | Zero passed / failed |',
        '|---|---:|---:|---:|---:|']
    for name,g in summary['coverage'].items():
        lines.append(f"| {name} | {g['members']} | {g['matched_models']} | {g['arms']['fitted-c']['passed']} / {g['arms']['fitted-c']['failed']} | {g['arms']['zero-c']['passed']} / {g['arms']['zero-c']['failed']} |")
    lines+=['','| Member | Arm | Status | Called / attempts | Anchor Δ NLL | Gradient / tolerance | Additivity / tolerance | KKT | Objective / guarded / diagnostic / reconstruction seconds | Failure |',
            '|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for row in summary['rows']:
        for arm,a in row['arms'].items():
            costs=' / '.join(num(a[k]) for k in ('objective_elapsed_s','guarded_call_elapsed_s','diagnostic_elapsed_s','reconstruction_elapsed_s'))
            reason=str(a['error'] or row.get('error') or '').replace('|','&#124;').replace('\n',' ')
            lines.append(f"| {row['label']} | {arm} | {a['status']} | {a['actual_calls']} / {a['attempts'] if a['attempts'] is not None else 'unavailable'} | {num((a['anchor'] or {}).get('difference'))} | {num(a['gradient_max_tolerance_ratio'])} | {num(a['additive_tolerance_ratio'])} | {num((a['live_anchor_audit'] or {}).get('stationarity'))} | {costs} | {reason} |")
    lines+=['','| Member | Matched model | Input reconstruction seconds | Total member seconds |','|---|---|---:|---:|']
    for row in summary['rows']:
        lines.append(f"| {row['label']} | {row['matched_model']} | {num(row['input_reconstruction_elapsed_s'])} | {num(row['elapsed_s'])} |")
    lines+=['','A normalized discrepancy of one is the declared tolerance. Missing checks are unavailable, not zero. '
        'Failed calls retain measured costs. Objective time is inside guarded-call time, which is inside diagnostic time; '
        'do not add these nested costs. Reconstruction is reported separately. Totals are observed invocation times, not embedded-speed claims.',
        '', 'Exact model matching includes inference-array fingerprints, original local center and input binding; '
        'it does not imply equal c-arm endpoints. No spatial fit, quadrature or reference port was used. '
        'All failures and full-member denominators remain visible.',
        '', '[SUMMARY.json](SUMMARY.json) records per-call evidence, discrepancies, costs and receipt/claim hashes. '
        'Protocol file SHA256 and canonical receipt digest are distinct. Raw receipt size is '+str(summary['raw_receipt_bytes'])+' bytes; '
        'hashes alone are not a standalone replay bundle.']
    return '\n'.join(lines)+'\n'


def plot(summary,path):
    if not summary.get('all12_terminal'):raise ValueError('full terminal report only')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(13,10),sharex=True)
    for i,row in enumerate(summary['rows']):
        for offset,arm,color in ((-.15,'fitted-c','#246c9c'),(.15,'zero-c','#bc6323')):
            a=row['arms'][arm];x=i+offset
            times=[1000*c['objective_elapsed_s'] for c in a['calls'] if c['called'] and finite(c['objective_elapsed_s'])]
            if times:axes[0].scatter([x]*len(times),times,c=color,s=14,alpha=.65)
            else:axes[0].text(x,.02,'missing',rotation=90,fontsize=7,transform=axes[0].get_xaxis_transform())
            for axis,key in zip(axes[1:],('gradient_max_tolerance_ratio','additive_tolerance_ratio')):
                v=a[key]
                if finite(v):axis.scatter(x,v,c=color,s=25)
                else:axis.text(x,.02,'missing',rotation=90,fontsize=7,transform=axis.get_xaxis_transform())
            if a['status']!='passed':axes[0].text(x,.85,'FAILED',rotation=90,color=color,fontsize=7,transform=axes[0].get_xaxis_transform())
    for axis,label in zip(axes,('Actual objective call (ms)','Gradient discrepancy / tolerance','Additivity discrepancy / tolerance')):
        axis.set_ylabel(label);axis.grid(axis='y',alpha=.2)
    for axis in axes[1:]:axis.set_yscale('symlog',linthresh=.001)
    for axis in axes[1:]:axis.axhline(1,color='#a33',linestyle='--')
    axes[0].scatter([],[],c='#246c9c',label='fitted-c');axes[0].scatter([],[],c='#bc6323',label='zero-c');axes[0].legend()
    axes[-1].set_xticks(range(len(summary['rows'])),[r['label'] for r in summary['rows']],rotation=45,ha='right')
    fig.suptitle('Consumed original endpoints: callback parity and cost, no position claim')
    fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--results',type=Path,default=HERE/'results');args=parser.parse_args()
    plan=json.loads(args.protocol.read_text())
    for name in ('report.py','test_report.py'):
        if str((HERE/name).relative_to(ROOT)) in plan['source_sha256']:raise ValueError('report unexpectedly inside frozen closure')
    summary=build(args.protocol,args.results)
    plot(summary,HERE/'parity_cost.png')
    for name,value in (('SUMMARY.json',json.dumps(summary,indent=2,allow_nan=False)),('RESULTS.md',markdown(summary))):
        with (HERE/name).open('x') as stream:stream.write(value)
    paths=[args.protocol,HERE/'SUMMARY.json',HERE/'RESULTS.md',HERE/'parity_cost.png',Path(__file__),HERE/'test_report.py']
    with (HERE/'REPORT_INTEGRITY.json').open('x') as stream:
        json.dump({'artifact_sha256':{str(p):sha(p) for p in paths},'receipt_sha256':summary['artifact_sha256']},stream,indent=2)


if __name__=='__main__':main()
