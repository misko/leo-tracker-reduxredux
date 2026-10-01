"""Complete-panel stratified, matched-prefix and runtime analysis; no tuning."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE=Path(__file__).resolve().parent


def statistics(rows):
    errors=[r['error_m'] for r in rows if r['accepted']]
    assert all(e is not None and np.isfinite(e) and e>=0 for e in errors)
    result=dict(planned=len(rows),accepted=len(errors),failed=len(rows)-len(errors),
        median_error_m=float(np.median(errors)) if errors else None,
        p90_error_m=float(np.percentile(errors,90)) if errors else None,
        maximum_error_m=max(errors) if errors else None,
        within1000m=sum(e<=1000 for e in errors),within3000m=sum(e<=3000 for e in errors))
    for field in ['runtime_s','cpu_s','recording_span_s','runtime_per_scan_s']:
        values=[r[field] for r in rows if r.get(field) is not None]
        result[field]=dict(known=len(values),median=float(np.median(values)) if values else None,
                          p90=float(np.percentile(values,90)) if values else None,maximum=max(values) if values else None)
    return result


def matched(rows,blocks):
    indexed={r['unit']:r for r in rows};result={}
    for a,b in [('S1','D1'),('S1','Q'),('D1','Q')]:
        common=[];target_only=source_only=neither=0
        for block in blocks:
            source,target=indexed[block+'-'+a],indexed[block+'-'+b]
            if source['accepted'] and target['accepted']:
                common.append(dict(block=block,source_error_m=source['error_m'],target_error_m=target['error_m'],
                                   change_m=target['error_m']-source['error_m']))
            elif target['accepted']:target_only+=1
            elif source['accepted']:source_only+=1
            else:neither+=1
        result[a+'_to_'+b]=dict(planned=len(blocks),both_accepted=len(common),target_only_accepted=target_only,
            source_only_accepted=source_only,neither_accepted=neither,
            improved=sum(r['change_m']<0 for r in common),worsened=sum(r['change_m']>0 for r in common),
            median_change_m=float(np.median([r['change_m'] for r in common])) if common else None,rows=common)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert Path(args.name).name==args.name
    output=HERE/(args.name+'.json');assert not output.exists() and not output.with_suffix('.png').exists()
    inputs={}
    def load(path):
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        inputs[str(path)]=digest(path);return json.loads(path.read_text())
    selection=load(HERE/'selection.json');units={u['unit_id']:u for u in selection['evaluation_units']}
    captures={c['unit_id']:c for c in selection['captures']}
    blocks=list(dict.fromkeys(u['block_id'] for u in units.values()));assert len(blocks)==16 and len(units)==112
    rows=[]
    for block in blocks:
        path=HERE/'independent-v2'/block/'evaluation.json';data=load(path)['rows']
        assert len(data)==7 and {r['unit'] for r in data}=={u for u,v in units.items() if v['block_id']==block}
        for original in data:
            row=dict(original);unit=units[row['unit']]
            assert row['scans']==unit['scans'] and row['size']==unit['size']
            row['dataset']=captures[row['scans'][0]]['dataset']
            assert all(captures[s]['dataset']==row['dataset'] for s in row['scans'])
            row['recording_span_s']=(max(captures[s]['capture_end_utc_ns'] for s in row['scans'])-
                                     min(captures[s]['capture_start_utc_ns'] for s in row['scans']))/1e9
            row['runtime_per_scan_s']=row['runtime_s']/row['size'] if row.get('runtime_s') is not None else None
            rows.append(row)
    assert len(rows)==112
    datasets=sorted({r['dataset'] for r in rows});summary={}
    for dataset in ['all',*datasets]:
        summary[dataset]={str(size):statistics([r for r in rows if r['size']==size and (dataset=='all' or r['dataset']==dataset)]) for size in [1,2,4]}
    comparisons=matched(rows,blocks)
    result=dict(summary=summary,matched_prefixes=comparisons,rows=rows,input_sha256=inputs,summarizer_sha256=digest(__file__),
        qualification='Full frozen development panel; no heldout claim. Errors conditional on acceptance, threshold counts use planned denominators. Prefix comparisons retain asymmetric failures. All112 windows are correlated within16quads and potentially across nearby blocks. Runtime starts from prepared tracks/orbits and excludes their original extraction/propagation and later audit.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),constrained_layout=True)
    by_id={r['unit']:r for r in rows}
    for ax,dataset in zip(axes,datasets):
        selected=[b for b in blocks if by_id[b+'-S1']['dataset']==dataset]
        for block in selected:
            chosen=[by_id[block+suffix] for suffix in ['-S1','-D1','-Q']]
            ax.plot([0,1,2],[r['error_m'] if r['accepted'] else np.nan for r in chosen],'-o',label=block,alpha=.85)
        ax.set_xticks([0,1,2],['First scan','First pair','Quad']);ax.set_title(str(dataset))
        ax.set_ylabel('Horizontal error (m)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('All16 matched prefixes from the frozen development panel\nMissing endpoints are unresolved fits; axis scales differ by dataset',fontsize=12)
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(dict(summary=summary,matched={k:{kk:vv for kk,vv in v.items() if kk!='rows'} for k,v in comparisons.items()}),indent=2),flush=True)


if __name__=='__main__':main()
