"""Validate FIR-bank indexing and candidate coverage on saved 2.5 MS/s IQ.

Uses NumPy's double-precision full convolution with FP32 operands, not the
proposed ARM float overlap-save kernel. No runtime claim follows from this test.
"""
import hashlib
import json
from pathlib import Path

import numpy as np


def peaks(grid):
    entries=[]
    for f,row in enumerate(grid):
        left=np.r_[-np.inf,row[:-1]];right=np.r_[row[1:],-np.inf]
        for epoch in np.flatnonzero((row>=left)&(row>=right)&((row>left)|(row>right))):
            entries.append((float(row[epoch]),f,int(epoch)))
    entries.sort(key=lambda x:(-x[0],abs(-400000+80000*x[1]),x[2]))
    keep=[];n=grid.shape[1]
    for value in entries:
        if all(value[1]!=other[1] or min(abs(value[2]-other[2]),n-abs(value[2]-other[2]))>=5 for other in keep):
            keep.append(value)
            if len(keep)==8:break
    return keep


def main():
    folder=Path('/var/tmp/leo-arm-full-search-oracle-allrates')
    baseline=Path('reports/2026_09_28_arm_conditioned_czt/arm-allrates-v3')
    manifest=json.loads((folder/'oracle.json').read_text());results=[]
    for case in manifest['cases']:
        rate=case['context']['rate_hz']
        if rate!=2500000:continue
        t=case['templates']['exact'];template=np.fromfile(folder/t['file'],dtype='<c16')
        assert hashlib.sha256((folder/t['file']).read_bytes()).hexdigest()==t['sha256']
        n=len(template)
        for rx in case['receivers']:
            ref=rx['raw_probe'];path=folder/ref['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==ref['sha256']
            x=np.fromfile(path,dtype='<c16');scale=max(abs(x.real).max(),abs(x.imag).max());x/=scale
            count=len(x);length=1<<(count+45-2).bit_length()
            input_fft=np.fft.fft(x.astype(np.complex64),length)
            # Preserve C's left-associated energy-prefix additions.
            prefix=np.empty(count+1);prefix[0]=0
            for k in range(count):prefix[k+1]=(prefix[k]+x[k].real*x[k].real)+x[k].imag*x[k].imag
            sums=np.zeros((11,n),np.float32);support=np.zeros(n,np.int32)
            for symbol in range(12):
                begin=round((2+26*symbol)*rate*4.4e-6);end=round((3+26*symbol)*rate*4.4e-6)
                t=template[begin:end];taps=len(t);te=np.sum(abs(t)**2)
                correlations=[]
                for f in range(11):
                    operand=(t*np.exp(2j*np.pi*(-400000+80000*f)*np.arange(taps)/rate)).astype(np.complex64)
                    h=np.conj(operand[::-1])
                    full=np.fft.ifft(input_fft*np.fft.fft(h,length))
                    correlations.append(abs(full[taps-1:count]).astype(np.float32))
                correlations=np.asarray(correlations)
                for frame in range(16):
                    base=begin+round(frame*(rate/750))
                    valid=min(n,count-taps+1-base)
                    if valid<=0:break
                    positions=base+np.arange(valid)
                    energy=np.maximum(0,prefix[positions+taps]-prefix[positions])
                    denom=np.sqrt(te*energy)
                    inverse=np.zeros(valid,np.float32);np.divide(1,denom,out=inverse,where=denom>0)
                    sums[:,:valid]+=correlations[:,positions]*inverse
                    support[:valid]+=1
            grid=sums.astype(float)/support
            label=f"{rate}-{case['context']['target']['edge']}-rx{rx['receiver_id']}"
            exact=np.fromfile(baseline/(label+'.f64'),dtype='<f8').reshape(11,n)
            selected=peaks(grid);expected=peaks(exact);guard=128*np.finfo(np.float32).eps
            threshold=selected[-1][0]-2*guard
            mask=grid>=threshold
            neighbors=mask.copy();neighbors[:,1:]|=mask[:,:-1];neighbors[:,:-1]|=mask[:,1:]
            results.append(dict(label=label,grid_cells=int(grid.size),max_grid_error=float(abs(grid-exact).max()),selected_peaks=[[f,e] for _,f,e in selected],reference_peaks=[[f,e] for _,f,e in expected],same_peak_inventory=[(f,e) for _,f,e in selected]==[(f,e) for _,f,e in expected],guarded_cells=int(mask.sum()),guarded_cells_with_neighbors=int(neighbors.sum()),all_reference_peaks_guarded=all(mask[f,e] for _,f,e in expected)))
    result=dict(scope=__doc__,results=results,all_inventory_equal=all(r['same_peak_inventory'] for r in results),all_reference_peaks_guarded=all(r['all_reference_peaks_guarded'] for r in results))
    Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    assert result['all_reference_peaks_guarded']


if __name__=='__main__':main()
