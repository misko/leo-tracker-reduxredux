"""Synthetic support illustration; no recordings, fitting or location evaluation."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from grouping import group_support


def main():
    root=Path(__file__).resolve().parent
    identity=dict(session_id='synthetic',input_manifest_sha256='synthetic-capture',
                  raw_recording_authority_digest='synthetic-raw',radio_id='synthetic-radio',
                  stream_generation='synthetic-stream',sample_rate_hz=1_000_000)
    rows=[]
    for visit in range(16):
        for receiver in (0,1):
            index=len(rows)
            start=visit*100
            end=start+(121 if visit==1 else 30)
            rows.append(dict(index=index,visit_index=visit,receiver=receiver,probe_index=0,
                             window_id=f'window-{index}',candidate_id=f'candidate-{index}',
                             support_status='available',support_reason=None,
                             device_sample_start=start,device_sample_end=end))
    support=dict(rows=rows,observations=len(rows),available=len(rows),unavailable_reasons={})
    result=group_support(support,identity,seed='159-synthetic-illustration')
    assert result['row_fold'][2:6]==[result['row_fold'][2]]*4
    (root/'SYNTHETIC_GROUPS.json').write_text(json.dumps(result,indent=2)+'\n')
    colors=['#2074a5','#de8a28']
    fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
    for row,fold in zip(rows,result['row_fold']):
        y=row['visit_index']+(row['receiver']-.5)*.25
        ax.barh(y,row['device_sample_end']-row['device_sample_start'],
                left=row['device_sample_start'],height=.2,color=colors[fold])
    ax.set(xlabel='Synthetic device-sample counter',ylabel='Visit (two bars = paired receivers)',
           title='Synthetic grouping: paired and overlapping support stay together')
    ax.set_yticks(range(16));ax.invert_yaxis()
    ax.legend(handles=[Patch(color=colors[i],label=f'Fold {i}') for i in (0,1)],loc='lower left')
    ax.grid(axis='x',alpha=.2)
    fig.savefig(root/'grouping.png',dpi=160)
    print(json.dumps(dict(rows=len(rows),groups=result['group_count'],fold_rows={k:len(v) for k,v in result['folds'].items()})))


if __name__=='__main__':main()
