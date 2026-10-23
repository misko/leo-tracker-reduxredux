"""Regenerate common draws and replay every saved synthetic endpoint."""
import numpy as np
from probe_worst_mechanisms import OUT, context, synthetic, VARIANTS, ARMS
from ds23_synthetic_known_nuisance import known_problem, attach_known_predictive
from ds23_frequency_events import make_event_problem, attach_event_predictive
from run_algo01_ds23_sample import read, write


def main():
    audits=[]
    for path in sorted((OUT/'synthetic').glob('DS23-*.json')):
        record=read(path);assert record['status']=='complete'
        d=context(record['case'])
        scan,node,entries,truth,noise=synthetic(d,record['site_index'],record['draw'],record['variant'])
        assert noise==record['noise']
        for arm in ARMS:
            saved=record['arms'][arm];reference=np.array(saved['phase_reference'])
            if record['variant'] in ('noise_only','all_nuisance'):
                p=make_event_problem(scan,node,d['keep'],arm,reference,d['powers'],d['means'],d['model'],[])
                attach_event_predictive(p,entries,d['powers'])
            else:
                p=known_problem(scan,node,d['keep'],arm,reference,d['powers'],d['means'],d['model'],truth,VARIANTS[record['variant']])
                attach_known_predictive(p,entries,d['powers'],truth,VARIANTS[record['variant']])
            x=np.array(saved['endpoint_east_north_km']);c=p.calculate(x)
            difference=float(c['negative_twice_elbo']-saved['negative_twice_elbo'])
            assert abs(difference)<1e-6
            phase=p.state(x)['phases'][p.labels]
            expected=d['means'] if record['variant']=='noise_only' else np.array(truth['true_phases_s'])
            active=np.unique(p.flat_labels[p.keep])
            audits.append(dict(case=record['case'],site_index=record['site_index'],draw=record['draw'],
                variant=record['variant'],arm=arm,objective_replay_difference=difference,
                active_phase_RMSE_s=float(np.sqrt(np.mean((phase[active]-expected[active])**2))),
                largest_absolute_active_phase_s=float(max(abs(phase[active]))),
                final_phase_change_s=saved['final_phase_change_s']))
    assert len(audits)==120
    write(OUT/'evidence/synthetic_replay.json',dict(rows=audits,all_120_endpoints_replayed=True,
        maximum_absolute_objective_replay_difference=max(abs(r['objective_replay_difference']) for r in audits),
        max_final_phase_change_s=max(r['final_phase_change_s'] for r in audits)))
    print('120 endpoints replayed; maximum phase change',max(r['final_phase_change_s'] for r in audits),flush=True)


if __name__=='__main__':main()
