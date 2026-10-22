"""Independently replay every native temporal endpoint in bounded iteration011."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration011_parent_choice as choice
from audit_ds23_family_cavity import density
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay,assert_linear_gate_replay
from leo.analysis.research.retained_track_likelihood import profile
from run_algo01_ds23_sample import read,write,sha


def main():
    choice.runner.configure();choice.paths.runner=choice.runner
    out=choice.runner.RAW/'temporal_endpoint_audit.json'
    if out.exists():raise FileExistsError('preserve temporal endpoint audit')
    rows=[]
    for variant,folder,parent in [('original_parent','graph_seeded_paths_v2',choice.ORIGINAL_PARENT),
                                   ('RF_parent','same_mask_parent_choice/paths',choice.selected_parent)]:
        for case in read(choice.runner.RAW/'protocol.json')['cases']:
            d,cov,kind,_=parent(case);source=choice.runner.RAW/folder/(case+'.json')
            for method,trial in read(source)['methods'].items():
                if 'arms' not in trial:continue
                fragments=read(source.parent/(case+'_'+method+'_selection.json'))['selected']
                scan,entries=choice.paths.native.append_native_paths(d['scan'],d['entries'],fragments,choice.paths.native.receiver_basis(d['scan']))
                dd=dict(d,scan=scan,entries=entries)
                for arm,saved in trial['arms'].items():
                    p=choice.paths.build(dd,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
                    delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
                    if abs(delta)>1e-5:raise ValueError('temporal objective no longer replays')
                    check=density(dd,p,x,dd['means'],entries);gates=summary(p,x,entries)
                    assert_curved_gate_replay(saved['gates'],gates['gates'])
                    for old,new,entry,sl in zip(saved['linear_gates'],gates['linear_gates'],entries,p.linear_slices,strict=True):
                        residual=c['linear_raw_prediction_residual_hz'][sl]
                        terms=profile(residual,np.zeros(len(residual)),*p.scan.white[entry['track_index']],bias_sigma=300.)
                        assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
                    coverage=choice.paths.coverage(dd,kind,arm,saved)
                    if set(coverage['accepted_observation_ids'])!=set(trial['coverage'][arm]['accepted_observation_ids']):
                        raise ValueError('temporal membership no longer replays')
                    if not all(np.array_equal(scan.times[ix],t['times']) for t,ix in zip(scan.tracks,scan.index,strict=True)):
                        raise ValueError('native timestamps do not map exactly')
                    rows.append(dict(variant=variant,case=case,method=method,arm=arm,accepted=trial['accepted'],
                        objective_difference=delta,all_gates_and_unique_IDs_replayed=True,exact_native_times=True,
                        source_sha256=sha(source),**check))
    write(out,dict(rows=rows,all_passed=True,reference_GPS_used=False,source_sha256=sha(Path(__file__))))
    print('Fresh temporal density, covariance, gates and membership checks:',len(rows),flush=True)


if __name__=='__main__':main()
