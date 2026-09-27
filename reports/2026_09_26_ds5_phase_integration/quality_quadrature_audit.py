"""Bounded independent numerical reference for the next real-bank replay."""
import json
import numpy as np
from quality_offset_quadrature import offset_evidence
from causal_quality_accuracy import exact_evidence
from quality_mixture_accuracy import OUT
from segment_catalogue_trial import SCALES

def main():
    cases=[([0,3,1,60,40,15],[5,50],[False,False,True,False,False,False]),([0,1,50,100],SCALES,[False,True,False,False])];rows=[]
    for index,(r,scales,flags) in enumerate(cases):
        times=np.arange(len(r),dtype=float)
        for kind in ('stationary','generic','timing_informed'):
            exact=exact_evidence(np.array(r),scales,times,flags,kind)
            for n in (16,32,64,128,256,512):
                actual=float(offset_evidence(r,scales,times,flags,kind,nodes=n)[-1]);rows.append(dict(case=index,model=kind,nodes_per_proposal_component=n,exact=exact,quadrature=actual,error_nats=actual-exact,passes=abs(actual-exact)<.05))
    (OUT/'quadrature-audit.json').write_text(json.dumps(dict(protocol='Independent deterministic integration over static CFO offset with exact finite-state quality recursion. Proposal uses mean and median plus all scale widths from the declared warmup. Small-case audit only; not a real-bank replay.',cases=cases,comparisons=rows),indent=2)+'\n')
    print(json.dumps([r for r in rows if r['nodes_per_proposal_component']==512],indent=2))

if __name__=='__main__':main()
