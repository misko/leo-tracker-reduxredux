"""Reference-free cross-fold preference within a fixed RF arm."""
import math

HYPOTHESES = ('zero-c', 'fitted-c')
ARMS = ('zero-c', 'fitted-c')
TOLERANCE = 1e-6


def preferences(cells, labels):
    index = {}
    for cell in cells:
        key = (cell['label'],cell['hypothesis'],cell['mode'],cell['arm'])
        if key in index:raise ValueError('duplicate cell')
        index[key]=cell
    rows=[]
    for label in labels:
        for arm in ARMS:
            totals={};counts={};errors=[]
            for hypothesis in HYPOTHESES:
                values=[]; sizes=[]
                for mode, held in (('train0','1'),('train1','0')):
                    cell=index.get((label,hypothesis,mode,arm))
                    if cell is None or cell.get('status')!='qualified':
                        errors.append(hypothesis+'/'+mode+': unavailable fit');continue
                    score=(cell.get('scores') or {}).get(held)
                    if score is None or score.get('status')!='complete':
                        errors.append(hypothesis+'/'+mode+': unavailable held score');continue
                    value=score['nll']; count=score['observations']
                    if (not isinstance(value,(int,float)) or not math.isfinite(value)
                            or isinstance(count,bool) or not isinstance(count,int) or count<=0):
                        raise ValueError('invalid held NLL/count')
                    values.append(value);sizes.append(count)
                if len(values)==2:totals[hypothesis]=sum(values);counts[hypothesis]=sizes
            row=dict(label=label,arm=arm,status='incomplete',selected_hypothesis=None,
                     held_nll=totals,held_counts=counts,errors=errors,tolerance=TOLERANCE)
            if len(totals)==2:
                if counts['zero-c']!=counts['fitted-c']:raise ValueError('unmatched held observations')
                delta=totals['fitted-c']-totals['zero-c'];row['delta_nll']=delta
                if abs(delta)<=TOLERANCE:row['status']='tie'
                else:
                    row['status']='selected'
                    row['selected_hypothesis']='fitted-c' if delta<0 else 'zero-c'
            rows.append(row)
    return rows
