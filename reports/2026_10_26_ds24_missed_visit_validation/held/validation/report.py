"""One fixed held-application comparison; all methods remain separate."""
from collections import Counter
import csv
import json
from pathlib import Path
import time
import audit


def main():
    audit.bound();began=time.monotonic();here=audit.HERE
    cases=audit.read(audit.RAW/'protocol.json')['cases']
    documents=[audit.read(here/'case_audits'/(case+'.json'))for case in cases]
    assert all(d['all_passed']for d in documents)
    rows=[r for d in documents for r in d['cells']];assert len(rows)==576
    result=dict(receiver_cells=576,paired_windows=288,all_passed=True,
        original=sum(r['original']for r in rows),methods={m:audit.summary(rows,m)for m in audit.METHODS},
        CH58={m:audit.summary([r for r in rows if r['channel']>=5],m)for m in audit.METHODS},
        by_case={d['case']:d['counts']for d in documents},
        by_channel={str(ch):{m:audit.summary([r for r in rows if r['channel']==ch],m)for m in audit.METHODS}for ch in [1,4,5,6,7,8]},
        by_native_receiver={str(rx):{m:audit.summary([r for r in rows if r['native_receiver_id']==rx],m)for m in audit.METHODS}for rx in [0,1]},
        by_case_channel_receiver={f'{case}/CH{ch}/nativeRX{rx}':{m:audit.summary([r for r in rows if r['case']==case and r['channel']==ch and r['native_receiver_id']==rx],m)for m in audit.METHODS}
            for case in cases for ch in [1,4,5,6,7,8]for rx in [0,1]},
        unavailable_forecasts=dict(Counter(r['R01_forecast_status']for r in rows)),
        R02_forecast_statuses=dict(Counter(r['R02_forecast_status']for r in rows)),
        reader_seconds=sum(d['reader_seconds']for d in documents),
        R01_scoring_seconds=sum(d['R01_scoring_seconds']for d in documents),
        R02_scoring_seconds=sum(d['R02_scoring_seconds']for d in documents),
        summed_producer_process_seconds=sum(d['producer_process_seconds']for d in documents),
        failed_windows=[w for d in documents for w in d['failures']],
        new_IQ_reads=0,new_scoring_calls=0,new_position_calls=0,
        source_hashes={str(here/'case_audits'/(case+'.json')):audit.sha(here/'case_audits'/(case+'.json'))for case in cases})
    audit.write(here/'summary.json',result)
    flat=[]
    for row in rows:
        for method,value in row['methods'].items():
            flat.append(dict(prediction_id=row['prediction_id'],case=row['case'],channel=row['channel'],
                native_receiver_id=row['native_receiver_id'],display_receiver=row['display_receiver'],method=method,
                original=row['original'],unavailable=row['unavailable'],**value))
    fields=list(dict.fromkeys(k for row in flat for k in row))
    with (here/'cells.csv').open('x')as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    channels=[1,4,5,6,7,8];x=np.arange(6);fig,axes=plt.subplots(1,2,figsize=(12.4,4.2))
    base=[result['by_channel'][str(c)]['R01_search']['original']for c in channels]
    for j,(method,label,color)in enumerate([('original','Original','#6b7280'),('R01_search','Original + R01 search','#1d4ed8'),('R02_quadratic_or_fallback','Original + R02 point','#059669')]):
        values=base if method=='original'else[b+result['by_channel'][str(c)][method]['new']for b,c in zip(base,channels)]
        axes[0].bar(x+(j-1)*.25,values,.24,label=label,color=color)
    axes[0].set_ylabel('Detected owners / 96 held cells per channel');axes[0].set_title('Additions preserve every original detection')
    for j,(method,label,color)in enumerate([('R01_search','R01 search','#1d4ed8'),('R02_quadratic_or_fallback','R02 point','#059669')]):
        zero=[result['by_channel'][str(c)][method]['new_zero_bin']for c in channels]
        other=[result['by_channel'][str(c)][method]['new']-z for c,z in zip(channels,zero)]
        axes[1].bar(x+(j-.5)*.34,zero,.32,label=label+' zero bin',color=color,alpha=.42)
        axes[1].bar(x+(j-.5)*.34,other,.32,bottom=zero,label=label+' nonzero bin',color=color)
    axes[1].set_ylabel('New original-negative admissions');axes[1].set_title('Frequency innovations remain donor-centered')
    for ax in axes:
        ax.set_xticks(x,[f'CH{c}'for c in channels]);ax.spines[['right','top']].set_visible(False);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Frozen held application: R01 split confirmation vs R02 full-window primary point',fontsize=12)
    fig.tight_layout();fig.savefig(here/'held_comparison.png',dpi=170);fig.savefig(here/'held_comparison.pdf');plt.close(fig)
    audit.write(here/'report_receipt.json',dict(summary_sha256=audit.sha(here/'summary.json'),
        figure_sha256=audit.sha(here/'held_comparison.png'),seconds=time.monotonic()-began))
    print(json.dumps({k:result[k]for k in ['original','methods','CH58','reader_seconds','R01_scoring_seconds','R02_scoring_seconds','failed_windows']}),flush=True)


if __name__=='__main__':main()
