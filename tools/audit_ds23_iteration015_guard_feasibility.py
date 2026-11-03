"""Independent original-gate and membership replay of guarded feasible recovery."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration015_recovery as binding
import probe_ds23_iteration015_guard_parent as guard
from audit_ds23_iteration013_recovery import check
from run_algo01_ds23_sample import read,write,sha


def main():
    folder=guard.OUT/'temporal_feasibility';out=folder/'independent_replay.json'
    if out.exists():raise FileExistsError('preserve guarded feasible replay')
    assert read(folder/'execution.json')['all_passed'];binding.configure('paths');rows=[]
    for case in read(binding.runner.RAW/'protocol.json')['cases']:
        t=read(folder/(case+'.json'))
        if 'arms' not in t:continue
        d,cov,kind,_=guard.parent(case);scan,entries=binding.paths.paths.native.append_native_paths(d['scan'],d['entries'],t['selected_paths'],binding.paths.paths.native.receiver_basis(d['scan']));dd=dict(d,scan=scan,entries=entries)
        for arm,s in t['arms'].items():
            p=binding.paths.paths.build(dd,kind,arm,s['phase_reference']);rows.append(check(dd,p,arm,s,'guard_constrained'))
            replay=binding.paths.paths.coverage(dd,kind,arm,s)
            if set(replay['accepted_observation_ids'])!=set(t['coverage'][arm]['accepted_observation_ids']):raise ValueError('guard-constrained native IDs changed')
            if t['accepted'] and not set(cov[arm]['accepted_observation_ids'])<=set(replay['accepted_observation_ids']):raise ValueError('accepted guard-constrained result drops parent IDs')
    write(out,dict(rows=rows,all_passed=True,source_sha256=sha(Path(__file__)),no_new_fit_or_GPS=True))
    print('Guard-constrained independent endpoint arms',len(rows),flush=True)


if __name__=='__main__':main()
