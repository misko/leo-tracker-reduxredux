"""Diagnose proposal recall against independently reviewed supported positions."""
import ctypes as c
import json
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_cpu_coarse import integer_grid,bank,Workspace,POLL
from diagnose_live_observer3_alignment import BASE,digest


def main():
    manifest=json.loads((BASE/'combined-pilot-controls-v1/result.json').read_text())
    track=json.loads((BASE/'adjacent-c-trend-long-v1.json').read_text())
    track=next(r['measurements'] for r in track['cases'] if r['label']=='positive' and r['feedback'])
    lib=c.CDLL(str(BASE/'saved-visit-coarse-replay.so'))
    lib.glrt_cpu_coarse_select.argtypes=[c.POINTER(Workspace),POLL,c.c_void_p]
    poll=POLL(lambda _:0)
    cases=[]
    for case in manifest['cases']:
        if case['label']!='positive':continue
        offset=case['source_offset']
        supported=[r for r in track if offset+22<=r.get('start',-1)<offset+3333 and r.get('rejection')==0]
        if not supported:continue
        path=BASE/'combined-pilot-controls-v1'/f"positive-{case['number']}"/'iq.ci16'
        assert digest(path)==case['input_sha256']
        iq=np.fromfile(path,dtype='<i2').reshape(-1,2)
        grid=integer_grid(iq[:14000],bank()).astype('<u4')
        work=Workspace();c.memmove(c.addressof(work.grid),grid.ctypes.data,grid.nbytes);work.completed_epochs=3333
        assert lib.glrt_cpu_coarse_select(c.byref(work),poll,None)==0
        candidates=[]
        for f in range(11):
            for epoch in range(3333):
                value=int(grid[f,epoch]);left=int(grid[f,epoch-1]) if epoch else 0
                right=int(grid[f,epoch+1]) if epoch<3332 else 0
                if value and value>=left and value>=right and not value==left==right:
                    candidates.append((epoch,f,value))
        candidates.sort(key=lambda r:(-r[2],abs(r[1]-5),r[0],r[1]))
        selected=[]
        for row in candidates:
            if any(min(abs(row[0]-p[0]),3333-abs(row[0]-p[0]))<20 and abs(row[1]-p[1])<=1 for p in selected):continue
            selected.append(row)
            if len(selected)==512:break
        assert selected[:8]==[(p.epoch,p.frequency,p.score) for p in work.peaks]
        assert selected[case['proposal']['selected']][0]==case['proposal']['epoch']
        targets=[]
        for row in supported:
            target=row['start']-offset-22
            hits=[i+1 for i,p in enumerate(selected) if min(abs(p[0]-target),3333-abs(p[0]-target))<=8]
            targets.append(dict(frame=row['frame'],pilot_offset=row['start']-offset,coherence=row['coherence'],
                                first_candidate_rank=hits[0] if hits else None))
        cases.append(dict(cut=case['number'],selected_eight=selected[:8],targets=targets))
        print(case['number'],[(r['frame'],r['first_candidate_rank']) for r in targets],flush=True)
    with (BASE/'positive-proposal-coverage-v1.json').open('x') as stream:
        json.dump(dict(scope='coarse_proposal_rank_near_reviewed_supported_timing',cases=cases,
            maximum_candidates_examined=512,coarse_frequency_not_a_requirement=True,
            native_tracking_qualified=False,acceptance_gates_changed=False,new_rf_samples=0,
            source_sha256=digest(Path(__file__))),stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
