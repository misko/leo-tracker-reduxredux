"""Independent replay of the bounded augmented-family experiment."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration014_augmented_family as study
from audit_ds23_iteration013_recovery import check
from ds23_frequency_events import make_event_problem,attach_event_predictive
from run_algo01_ds23_sample import read,write,sha


def main():
    out=study.OUT/'independent_replay.json'
    if out.exists():raise FileExistsError('preserve augmented-family replay')
    assert read(study.OUT/'execution.json')['all_passed'];study.runner.configure();rows=[]
    for case in read(study.OUT/'protocol.json')['cases']:
        d=study.runner.engine.current_setup(case)
        for i,t in enumerate(read(study.OUT/(case+'.json'))['trials']):
            dd=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'])
            for arm,s in t['arms'].items():
                p=make_event_problem(dd['scan'],dd['node'],dd['keep'],arm,np.asarray(s['phase_reference']),dd['powers'],dd['means'],dd['model'],[]);attach_event_predictive(p,dd['entries'],dd['powers'])
                rows.append(check(dd,p,arm,s,'augmented_family_'+str(i)))
    write(out,dict(rows=rows,all_passed=True,no_new_fit_or_GPS=True,source_sha256=sha(Path(__file__))))
    print('Augmented-family independent arm replays',len(rows),flush=True)


if __name__=='__main__':main()
