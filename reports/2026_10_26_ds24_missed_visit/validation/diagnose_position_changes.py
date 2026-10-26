"""Existing-output attribution/identity audit; no refit, tuning or new RF."""
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
import recovery
from leo.analysis.research.retained_track_likelihood import PERIOD


def read(p):return json.loads(Path(p).read_text())


def mapping(root,case):
    recovery.SOURCE=root;d=recovery.context(case);p=recovery.build(d,'c0',d['arms']['c0']['phase_reference'])
    observations={o['observation_id']:o for o in d['observations']};out={}
    for row,index,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=p.scan.tracks[index]
        for oid,value,active in zip(track['observation_ids'],track['values'],p.keep[sl],strict=True):
            if active:
                lift=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(alias)
                out[oid]=dict(role='curved',norad=int(p.scan.norads[row['candidate_index']]),alias_lift=lift)
    for entry in d['entries']:
        for oid in entry['observation_ids']:
            assert oid not in out
            out[oid]=dict(role='predictive',norad=int(p.scan.norads[entry['candidate_index']]),
                alias_lift=int(entry.get('alias',0)))
    noise=read(root/case/'radio_noise.json')
    effective={oid:noise['per_observation_noise_sigma_hz'][oid] if noise['extra_parameter_BIC_gain']>0 else noise['constant_radio_sigma_hz'] for oid in observations}
    return out,effective


def main():
    assert read(HERE/'position_inference_audit.json')['all_complete']
    info=read(HERE/'frequency_information_12cases.json');byid={r['target_observation_id']:r for r in info['natural_rows']}
    cases=[]
    for case in ('DS24-0011','DS24-0097'):
        root=HERE/'position_runs'/case
        base,base_noise=mapping(root/'baseline',case)
        proxy,proxy_noise=mapping(root/'additions_proxy',case)
        floor,floor_noise=mapping(root/'additions_bin_floor',case)
        ledger=read(HERE/(case+'_additions.json'));added={r['target_observation_id']:r for r in ledger['staged']}
        incumbents=set(base_noise)
        identities=[]
        for oid in sorted(set(added)&set(proxy)):
            a=added[oid];f=byid[oid]
            identities.append(dict(observation_id=oid,prediction_id=a['prediction_id'],channel=a['channel'],
                receiver=a['receiver'],native_receiver_id=a['native_receiver_id'],
                start_counter=a['native']['start_counter'],stop_counter=a['native']['stop_counter'],
                reference_counter=a['reference_counter'],measured_cfo_hz=f['measured_CFO_hz'],
                earlier_predicted_cfo_hz=f['predicted_CFO_hz'],residual_fft_bin_hz=f['residual_bin_hz'],
                donor_count=f['donor_count'],confirmation_margin=a['confirmation_margin'],
                assigned_role=proxy[oid]['role'],assigned_norad=proxy[oid]['norad'],
                total_native_alias_lift=proxy[oid]['alias_lift'],proxy_sigma_hz=proxy_noise[oid],floor_sigma_hz=floor_noise[oid]))
        cases.append(dict(case=case,new_likelihood_identities=identities,
            baseline_to_proxy=dict(retained_likelihood_IDs=len(set(base)&set(proxy)),lost_likelihood_IDs=sorted(set(base)-set(proxy)),
                gained_incumbent_likelihood_IDs=sorted((set(proxy)-set(base))-set(added)),
                reassigned_retained_likelihood_IDs=[oid for oid in set(base)&set(proxy) if base[oid]!=proxy[oid]],
                incumbent_noise_changed=sum(abs(proxy_noise[oid]-base_noise[oid])>1e-10 for oid in incumbents),
                incumbent_noise_change_range_hz=[min(proxy_noise[oid]-base_noise[oid] for oid in incumbents),max(proxy_noise[oid]-base_noise[oid] for oid in incumbents)]),
            proxy_to_floor=dict(likelihood_ID_sets_equal=set(proxy)==set(floor),
                reassigned_retained_likelihood_IDs=[oid for oid in set(proxy)&set(floor) if proxy[oid]!=floor[oid]],
                incumbent_noise_scales_exactly_equal=all(proxy_noise[oid]==floor_noise[oid] for oid in incumbents),
                new_likelihood_owner_noise_changes={oid:floor_noise[oid]-proxy_noise[oid] for oid in set(added)&set(proxy)})))
    with (HERE/'position_attribution.json').open('x') as stream:
        json.dump(dict(cases=cases,new_fit_calls=0,new_RF_calls=0,
            interpretation='Proxy-to-floor changes only new diagonal scales; inspect any likelihood-map changes. Baseline-to-proxy also relearns incumbent proxy scales, so complete attribution needs a separate fixed-incumbent counterfactual not run here.'),stream,indent=2);stream.write('\n')
    print(json.dumps(cases,indent=2))


if __name__=='__main__':main()
