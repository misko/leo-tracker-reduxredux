"""Replay the matched no-event denominators, including newly fitted support nulls."""

from pathlib import Path
import numpy as np

import audit_ds23_iteration013_recovery as audit
from run_algo01_ds23_sample import read,write,sha


def main():
    audit.binding.configure('paths');out=audit.RAW/'step_null_audit.json'
    if out.exists():raise FileExistsError('preserve matched-null replay')
    rows=[]
    for case in read(audit.RAW/'protocol.json')['cases']:
        original=audit.binding.runner.engine.current_setup(case)
        for variant,folder in [('default','shared_step'),('support','supported_shared_step')]:
            seen=set()
            for trial in read(audit.RAW/folder/(case+'.json'))['trials']:
                signature=tuple(a['component'] for a in trial['additions'])
                if signature in seen:continue
                seen.add(signature);d=dict(original,node=trial['node'],keep=np.asarray(trial['mask'],bool),means=np.asarray(trial['means']),entries=trial['entries'])
                for arm,s in trial['null_arms'].items():
                    if variant=='support':p=audit.supported.build(original,trial,arm,s['phase_reference'],[])
                    else:
                        p=audit.make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(s['phase_reference']),d['powers'],d['means'],d['model'],[])
                        audit.attach_event_predictive(p,d['entries'],d['powers'])
                    rows.append(audit.check(d,p,arm,s,variant+'_matched_null_'+str(len(seen))))
    write(out,dict(rows=rows,all_passed=True,no_optimization_or_GPS=True,source_sha256=sha(Path(__file__))))
    print('Matched zero-event endpoint arms audited',len(rows),flush=True)


if __name__=='__main__':main()
