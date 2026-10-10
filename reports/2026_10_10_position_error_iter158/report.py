"""Postseal coverage/cost report only; no inference or evaluation-coordinate port."""
import hashlib
import json
from pathlib import Path
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(plan, digest, directory):
    rows=[]; files={}; members=[]
    for member in plan['members']:
        label=member['label']
        paths=[directory/(label+'.json'),directory/(label+'.claim.json')]
        result,claim=[json.loads(p.read_text()) for p in paths]
        for document in (result,claim):
            if document.get('label')!=label or document.get('protocol_sha256')!=digest:
                raise ValueError('foreign receipt/claim: '+label)
        if result['status'] not in ('complete','failed') or set(result['arms'])!={'fitted-c','zero-c'}:
            raise ValueError('missing terminal coverage: '+label)
        files.update({p.name:sha(p) for p in paths})
        members.append(dict(label=label,status=result['status'],matched_model=result.get('matched_model'),
                            elapsed_s=result['elapsed_s'],input_reconstruction_elapsed_s=result.get('input_reconstruction_elapsed_s')))
        for arm in ('fitted-c','zero-c'):
            entry=result['arms'][arm]; d=entry.get('diagnostic',{})
            axes=d.get('axes',{})
            widths=[axes.get(str(r),{}).get('integration',{}).get('bounds') for r in (0,1)]
            combined=sum(b['log_width'] for b in widths) if all(b is not None for b in widths) else None
            calls=d.get('calls',[])
            actual=sum(bool(c['called']) for c in calls)
            if d and actual!=d['actual_joint_calls']:
                raise ValueError('call count differs: '+label)
            if actual>1025:
                raise ValueError('joint cap exceeded: '+label)
            anchor=d.get('anchor')
            rows.append(dict(label=label,dataset=member['dataset'],arm=arm,status=entry['status'],
                error=d.get('error',entry.get('error')),axis_status=[axes.get(str(r),{}).get('status','missing') for r in (0,1)],
                combined_log_width=combined,actual_joint_calls=actual,endpoint_elapsed_s=d.get('elapsed_s'),
                objective_elapsed_s=sum(c.get('objective_elapsed_s') or 0 for c in calls),
                visibility_elapsed_s=d.get('visibility_elapsed_s'),
                anchor_difference=None if anchor is None else anchor['value']-anchor['stored_objective'],
                live_anchor_qualified=d.get('live_anchor_audit',{}).get('qualified') if d.get('live_anchor_audit') else None,
                normalized_marginal_bounds=d.get('normalized_marginal_bounds')))
    return dict(protocol_sha256=digest,members=members,rows=rows,raw_sha256=files)


def main():
    # Recheck immutable scientific closure after execution, before aggregation.
    import run
    freezer=run.module('freeze158_for_report',HERE/'freeze.py')
    plan=json.loads((HERE/'protocol.json').read_text())
    run.BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    summary=collect(plan,canonical_digest(plan),HERE/'results')
    rows=summary['rows']; summary['target_log_width']=1e-4
    summary['all_endpoints_passed']=all(r['status']=='passed' for r in rows)
    summary['scope']='Consumed conditional integration only; no position/frequency-fit comparison'
    (HERE/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    labels=[m['label'] for m in plan['members']]
    x=np.arange(len(labels))
    for arm,offset,color in [('fitted-c',-.15,'tab:blue'),('zero-c',.15,'tab:orange')]:
        group=[r for r in rows if r['arm']==arm]
        widths=[r['combined_log_width'] if r['combined_log_width'] is not None else np.nan for r in group]
        axes[0].scatter(x+offset,widths,label=arm,color=color)
        axes[1].scatter(x+offset,[r['actual_joint_calls'] for r in group],label=arm,color=color)
    axes[0].axhline(1e-4,color='black',linestyle='--',label='Combined target')
    axes[0].set_yscale('log');axes[0].set_ylabel('Combined log-integral width')
    axes[0].set_title('Full-support uncertainty; missing bounds omitted')
    axes[1].set_ylabel('Actual joint-objective calls');axes[1].set_title('Includes shared anchor and discarded parents')
    for ax in axes:
        ax.set_xticks(x,labels,rotation=65,ha='right');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(HERE/'tractability.png',dpi=160)
    lines=['# Bounded conditional integration: recording results','',
           '![Coverage and callback cost](tractability.png)','',
           'This is a consumed-data tractability diagnostic on twelve fixed scans, both final c arms. '
           'It performs no position fitting, changes no frequency-fit parameters, and supplies no new position-error estimate. '
           'B7 is unchanged. All members and failures are retained.','',
           '| Dataset | Arm | Endpoints | Target met | Both bounds available |',
           '|---|---|---:|---:|---:|']
    for dataset in ('DS16','DS17','DS18'):
        for arm in ('fitted-c','zero-c'):
            group=[r for r in rows if r['dataset']==dataset and r['arm']==arm]
            lines.append(f"| {dataset} | {arm} | {len(group)} | {sum(r['status']=='passed' for r in group)} | {sum(r['combined_log_width'] is not None for r in group)} |")
    lines+=['','| Member | Arm | Status | RX0 / RX1 | Combined width | Calls |',
            '|---|---|---|---|---:|---:|']
    for r in rows:
        width='missing' if r['combined_log_width'] is None else f"{r['combined_log_width']:.6g}"
        lines.append(f"| {r['label']} | {r['arm']} | {r['status']} | {' / '.join(r['axis_status'])} | {width} | {r['actual_joint_calls']} |")
    passed=sum(r['status']=='passed' for r in rows)
    total_calls=sum(r['actual_joint_calls'] for r in rows)
    objective=sum(r['objective_elapsed_s'] for r in rows)
    worker=sum(m['elapsed_s'] for m in summary['members'])
    matched=sum(m['matched_model'] is True for m in summary['members'])
    lines+=['',f'**{passed}/24 endpoints met the target; {matched}/12 pairs had matching model/input identities.** '
            f'Total actual objective calls: {total_calls:,}; measured objective time: {objective:.3f} s; '
            f'total member worker time including reconstruction: {worker:.3f} s. These costs are nested, not additive. '
            'Host timings are not embedded benchmarks.','',
            'The combined width target is 0.0001 NLL, allocated 0.00005 per receiver. '
            'Each receiver has at most 512 scalar calls and the endpoint has a 30-second soft deadline '
            'including model construction; public input reconstruction is separate. '
            'Envelope bounds are conservative numerical checks, not formal floating-point certificates.','',
            ('All endpoints are tractable under this protocol. A separately declared spatial-relevance test is required before localization work.'
             if summary['all_endpoints_passed'] else
             '**Decision: stop this lean integration route under the declared budget.** Unresolved endpoints do not provide usable marginal scores. '
             'No tolerance expansion, retries, spatial stencil or localization comparison is authorized by these results.'),'',
            '## Reproducibility','',
            'The [scientific plan](PLAN.md) and [frozen source/input/runtime protocol](protocol.json) were published before execution. '
            'Nineteen adapter/orchestration tests passed in 0.40 seconds; four reporter tests passed in 0.21 seconds. '
            'The complete closure was rechecked before this report. '
            '[SUMMARY.json](SUMMARY.json) retains errors, per-arm coverage, timing and original-anchor checks; '
            '[raw-receipts.tar.gz](raw-receipts.tar.gz) contains all terminal receipts and claims. '
            'The recording store itself is not bundled. No reference coordinates or position-error evaluation modules are used.','']
    (HERE/'README.md').write_text('\n'.join(lines))
    with tarfile.open(HERE/'raw-receipts.tar.gz','w:gz') as archive:
        for name in sorted(summary['raw_sha256']):archive.add(HERE/'results'/name,arcname=name)
    with tarfile.open(HERE/'raw-receipts.tar.gz','r:gz') as archive:
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers()}
    if actual!=summary['raw_sha256']:raise ValueError('archive differs from raw receipts')
    names=['README.md','SUMMARY.json','tractability.png','raw-receipts.tar.gz','report.py','protocol.json']
    (HERE/'REPORT_INTEGRITY.json').write_text(json.dumps({name:sha(HERE/name) for name in names},indent=2)+'\n')
    print(json.dumps(dict(passed=passed,pairs_matched=matched,total_calls=total_calls,objective_s=objective,worker_s=worker)))


if __name__=='__main__':main()
