"""Measure exact sample-normalization reuse between adjacent saved windows."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    folder=Path('/var/tmp/leo-ds7-large-arm-20260928')
    manifest=json.loads((folder/'inputs.json').read_text())
    totals=defaultdict(lambda:dict(dwells=0,adjacent_pairs=0,equal_scale_pairs=0,all_equal_receivers=0))
    details=[]
    for row in manifest['rows']:
        path=folder/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        iq=np.load(path,mmap_mode='r',allow_pickle=False)
        rate=row['rate_hz'];stride=rate//100;length=rate//50
        r=totals[rate];r['dwells']+=1
        scales=[]
        for rx in range(2):
            values=[]
            for probe in range(11):
                x=iq[probe*stride:probe*stride+length,rx,:]
                # Promote before negation, including the int16 -32768 case.
                values.append(max(int(x.max()),-int(x.min())))
            r['adjacent_pairs']+=10
            r['equal_scale_pairs']+=sum(a==b for a,b in zip(values,values[1:]))
            r['all_equal_receivers']+=len(set(values))==1
            scales.append(values)
        details.append(dict(ordinal=row['ordinal'],rate_hz=rate,scales=scales))
    for r in totals.values():
        r['equal_scale_fraction']=r['equal_scale_pairs']/r['adjacent_pairs']
    result=dict(input_manifest_sha256=hashlib.sha256((folder/'inputs.json').read_bytes()).hexdigest(),by_rate=dict(totals),details=details,note='Necessary condition for exact adjacent-window dot reuse; energies/support still require original per-window computation. This does not measure kernel runtime.')
    Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['by_rate'],indent=2))


if __name__=='__main__':main()
