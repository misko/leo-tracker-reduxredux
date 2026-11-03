"""Check the near competitor against its own already-assigned observations."""
import copy
import json
import numpy as np
from audit_n12_pair_identity import load,POSITIONS,OUT,ARMS,GRID,split_windows,predict,fit_candidate,write_csv


def main():
    full,meta,_=load('N12');base=json.loads((POSITIONS/'baseline.json').read_text());rows=[]
    for owners in ((62866,),(58868,),(62866,58868)):
        mask=np.isin(full.owners,owners);data=copy.copy(full)
        for k in ('times','measured','receiver','channel','rf','group','owners'):
            setattr(data,k,getattr(full,k)[mask].copy())
        ids=np.array([int(np.flatnonzero(full.numbers==n)[0]) for n in (62866,58868)])
        data.numbers=full.numbers[ids];data.position=full.position[ids];data.velocity=full.velocity[ids]
        params=np.zeros(8);params[:2]=base['arms']['fitted-c']['roof']['parameters'][:2]
        train=np.zeros(len(data.times),bool)
        for n in owners:
            use=data.owners==n;train[use]=split_windows(data.receiver[use],data.channel[use],20261005+n)
        coarse=np.empty((len(GRID),len(data.times),2));vis=np.empty(coarse.shape,bool)
        for ti,t in enumerate(GRID):
            for j in range(2):coarse[ti,:,j],vis[ti,:,j]=predict(data,j,t,params)
        for arm in ARMS:
            roof=base['arms'][arm]['roof'];p=np.array(roof['parameters'])
            observed=data.measured-p[2+2*data.receiver]-p[3+2*data.receiver]*(data.times-150.)-roof['coefficient']*(data.rf-meta['rf_center_hz'])/1e9
            for j in range(2):
                r=fit_candidate(data,j,observed,train,params,coarse,vis)
                if r is not None:rows.append(dict(window_owners='+'.join(map(str,owners)),windows=len(data.times),arm=arm,**r))
    write_csv('58868-competing-and-combined-windows.csv',rows)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
