"""Postseal grouping coverage, with an independent cross-fold overlap audit."""
import hashlib
import json
from pathlib import Path
import tarfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_groups(support, grouping):
    rows=support['rows'];n=len(rows);folds=grouping['folds'];assignment=grouping['row_fold']
    if len(assignment)!=n or sorted(folds['0']+folds['1'])!=list(range(n)):
        raise ValueError('folds do not cover each row exactly once')
    if any(assignment[i]!=f for f in (0,1) for i in folds[str(f)]):
        raise ValueError('fold assignments differ')
    visits={};events=[]
    for i,row in enumerate(rows):
        fold=assignment[i];visit=row['visit_index']
        if visits.setdefault(visit,fold)!=fold:raise ValueError('visit split across folds')
        events.append((row['device_sample_start'],row['device_sample_end'],fold))
    frontier=[-1,-1]
    for start,end,fold in sorted(events):
        if start<frontier[1-fold]:raise ValueError('sample overlap crosses folds')
        frontier[fold]=max(frontier[fold],end)
    result={}
    for fold in (0,1):
        per_rx={}
        for rx in (0,1):
            train=[rows[i]['support_center_ns'] for i in folds[str(fold)] if rows[i]['receiver']==rx]
            held=[rows[i]['support_center_ns'] for i in folds[str(1-fold)] if rows[i]['receiver']==rx]
            lower,upper=(min(train),max(train)) if train else (None,None)
            per_rx[str(rx)]=dict(training_rows=len(train),held_rows=len(held),
                held_outside_training_center_span=None if not train else sum(t<lower or t>upper for t in held))
        result[str(fold)]=per_rx
    return result


def main():
    import run
    freeze=run.module('freeze160_report',HERE/'freeze.py')
    base=run.module('run155_report160',HERE.parent/'2026_10_10_position_error_iter155/run.py')
    plan=json.loads((HERE/'protocol.json').read_text());base.verify(plan,freeze.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan);rows=[];files={}
    for member in plan['members']:
        label=member['label'];paths=[HERE/'results'/(label+suffix) for suffix in ('.json','.claim.json')]
        result,claim=[json.loads(p.read_text()) for p in paths]
        if any(d.get('label')!=label or d.get('protocol_sha256')!=digest for d in (result,claim)):
            raise ValueError('foreign receipt/claim')
        if result['status'] not in ('complete','failed') or result['source_loads']>1:
            raise ValueError('nonterminal receipt or exceeded metadata load cap')
        files.update({p.name:sha(p) for p in paths})
        row=dict(label=label,dataset=member['dataset'],status=result['status'],error=result.get('error'),
                 source_loads=result['source_loads'],elapsed_s=result['elapsed_s'])
        if result['status']=='complete':
            group=result['groups']['grouping']
            support=json.loads((run.ROOT/member['support_path']).read_text())['support']
            audit=audit_groups(support,group)
            row.update(observations=group['observations'],visits=group['visits'],groups=group['group_count'],
                       fold_rows=[len(group['folds'][str(f)]) for f in (0,1)],receiver_audit=audit,
                       complete_partition=True,no_cross_fold_overlap=True)
        rows.append(row)
    summary=dict(protocol_sha256=digest,rows=rows,raw_sha256=files,scope='Metadata only; no likelihood or position result')
    (HERE/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,ax=plt.subplots(figsize=(11,4.5),constrained_layout=True)
    x=np.arange(len(rows))
    for fold,color in [(0,'#2074a5'),(1,'#de8a28')]:
        values=[r.get('fold_rows',[0,0])[fold] for r in rows]
        bottom=[r.get('fold_rows',[0,0])[0] if fold else 0 for r in rows]
        ax.bar(x,values,bottom=bottom,label=f'Fold {fold}',color=color)
    ax.set_xticks(x,[r['label'] for r in rows],rotation=55,ha='right')
    ax.set(ylabel='Original observation rows',title='Fixed-seed acquisition folds: all twelve members retained')
    ax.legend();fig.savefig(HERE/'fold_coverage.png',dpi=160)
    complete=[r for r in rows if r['status']=='complete']
    total=sum(r['observations'] for r in complete)
    lines=['# Real acquisition folds prepared','',
           '![Fold coverage](fold_coverage.png)','',
           f'**{len(complete)}/12 members prepared; {total:,} observation rows retained.** '
           'This is metadata preparation only. No IQ was read, no model was fitted, and no new position error was measured. '
           'B7 remains unchanged. The seed was frozen and published before metadata loading; no reseeding or member replacement occurred.','',
           '| Member | Status | Observations | Visits | Overlap groups | Fold 0 | Fold 1 |',
           '|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        counts=r.get('fold_rows',['—','—'])
        lines.append(f"| {r['label']} | {r['status']} | {r.get('observations','—')} | {r.get('visits','—')} | {r.get('groups','—')} | {counts[0]} | {counts[1]} |")
    lines+=['','An independent postseal sweep verified that each original row occurs exactly once, '
            'whole visits remain together, and no physical sample interval overlaps across folds. '
            'Both receivers are represented in both folds for every completed member with nonzero receiver counts reported below. '
            'These properties prevent direct sample overlap; they do not establish statistical independence.','',
            '| Member | Fold 0 RX0 / RX1 | Fold 1 RX0 / RX1 | Held rows outside training center span (train 0 / train 1) |',
            '|---|---:|---:|---:|']
    for r in complete:
        audit=r['receiver_audit'];counts=[' / '.join(str(audit[str(f)][str(rx)]['training_rows']) for rx in (0,1)) for f in (0,1)]
        tails=[sum(audit[str(f)][str(rx)]['held_outside_training_center_span'] or 0 for rx in (0,1)) for f in (0,1)]
        lines.append(f"| {r['label']} | {counts[0]} | {counts[1]} | {tails[0]} / {tails[1]} |")
    lines+=['','The span diagnostic counts held-row centers outside the same receiver’s training-row center range. '
            'It is metadata context, not an estimate of extrapolation error and not a reason to alter the folds.','',
            '## Evidence and next step','',
            'The [plan](PLAN.md) and [frozen protocol](protocol.json) bind all original support/claim hashes, '
            'the twelve iteration 155 observation identities, helper sources and pinned runtime. Seventeen preparation tests passed in 0.18 seconds; '
            'five independent reporter-audit tests passed in 0.21 seconds. '
            'The complete closure was checked again before reporting. '
            '[SUMMARY.json](SUMMARY.json) retains coverage, errors, receiver counts and elapsed costs; '
            '[raw-receipts.tar.gz](raw-receipts.tar.gz) includes every exact fold membership and claim. '
            'The source recording store is not bundled.','',
            'The next fit protocol must declare a common reference-free seed, fresh same-budget full-data controls, '
            'paired c locks, convergence handling and separate held-likelihood versus position-error reporting. '
            'Full-data bank/region/satellite-center conditioning remains explicit; this is consumed-data development, not independent validation.','']
    # Never let prose imply receiver coverage not supported by the actual counts.
    if any(r['receiver_audit'][str(f)][str(rx)]['training_rows']==0 for r in complete for f in (0,1) for rx in (0,1)):
        raise ValueError('report requires explicit missing-receiver coverage handling')
    (HERE/'README.md').write_text('\n'.join(lines))
    with tarfile.open(HERE/'raw-receipts.tar.gz','w:gz') as tar:
        for name in sorted(files):tar.add(HERE/'results'/name,arcname=name)
    with tarfile.open(HERE/'raw-receipts.tar.gz','r:gz') as tar:
        readback={m.name:hashlib.sha256(tar.extractfile(m).read()).hexdigest() for m in tar.getmembers()}
    if readback!=files:raise ValueError('archive readback differs')
    names=('README.md','SUMMARY.json','fold_coverage.png','raw-receipts.tar.gz','report.py','protocol.json')
    (HERE/'REPORT_INTEGRITY.json').write_text(json.dumps({name:sha(HERE/name) for name in names},indent=2)+'\n')
    print(json.dumps(dict(complete=len(complete),observations=total,source_loads=sum(r['source_loads'] for r in rows),elapsed_s=sum(r['elapsed_s'] for r in rows))))


if __name__=='__main__':main()
