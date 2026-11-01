"""Whole-track prediction when receiver separation is absent or insufficient."""
import argparse
import numpy as np
import evaluate as e
from diagnostics import selected_context,transfer


def run(case):
    result=e.read(e.OUT/case/'result.json');rows=[]
    for method in ('reassociation_only','combined'):
        name=result['methods'][method]['selected']
        if not name or name=='complete_history':continue
        dd,z,record,d=selected_context(case,method);n=record['target'];new=record['hypothesis']['norad']
        screen=e.read(e.OUT/case/str(n)/'screen.json')
        for a in e.ARMS:
            point=np.asarray(screen['cavity'][a]['x'])
            for label,ctx,num in [('incumbent',d,n),('replacement',dd,new)]:
                rows += [dict(method=method,context=label,norad=num,**r) for r in transfer(ctx,z,num,point,a,mode='track')]
    e.write(e.OUT/case/'whole_track_transfer.json',dict(case=case,rows=rows,
        scope='Conditional held whole-track predictions; same RF cavity position, training-only phase refresh; graph/aliases/candidate discovery inherited from full data; no acceptance changes'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');run(p.parse_args().case)
