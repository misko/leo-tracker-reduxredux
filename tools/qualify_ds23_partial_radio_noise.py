"""Learn covariance without the target component, validate its RF contrasts."""

from pathlib import Path

import repair_ds23_iteration009_targets as repair
from ds23_other_track_noise import blocks,fit_shape,validation
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'other_track_radio_noise'


def main():
    repair.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve RF noise qualification')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),helper_sha256=sha(Path(fit_shape.__code__.co_filename)),
        cases=read(repair.runner.RAW/'protocol.json')['cases'],
        target='partially used curved component nominated by frozen partial-tail diagnostic',
        covariance_training='all other original graph components on the same physical receiver',
        target_component_original_measurement_IDs_excluded_from_covariance_training=True,
        shape='(1-alpha)I+alpha exp(-abs(dt)/tau)',alphas=[.1,.3,.6,.9],taus_s=[1,3,10,30,100],
        heteroscedastic_native_sigma_and_weighted_polynomial_REML_contrasts=True,
        minimum_training_pieces=10,training_gain_above2log_contrast_dimensions=True,
        target_RF_contrast_gain_must_be_positive_for_any_position_trial=True,
        no_satellite_residual_GPS_TLE_or_new_RF_used_for_noise_learning=True,
        no_position_observations_withheld=True))
    for case in read(OUT/'protocol.json')['cases']:
        d=repair.engine.current_setup(case);source=read(repair.runner.RAW/'partial_tail_diagnostic'/(case+'.json'));rows=[]
        meta=d['scan'].fixed_window_noise;lookup=meta['per_observation_noise_sigma_hz'] if meta['extra_parameter_BIC_gain']>0 else {}
        for target in source['rows']:
            track=d['scan'].tracks[target['source_track_index']];ids=set(track['observation_ids'])
            training=[t for t in d['scan'].tracks if t['receiver']==track['receiver'] and not ids&set(t['observation_ids'])]
            train_blocks=blocks(training,lookup,d['scan'].radio_sigma_hz);test_blocks=blocks([track],lookup,d['scan'].radio_sigma_hz)
            model=fit_shape(train_blocks);test=validation(test_blocks,model);train_ids={o for p in train_blocks for o in p['observation_ids']}
            if train_ids&ids:raise ValueError('target RF leaked into covariance learning')
            qualified=bool(model['qualified'] and test['positive_target_gain'])
            rows.append(dict(component=track['key'],track_index=target['source_track_index'],model=model,target_validation=test,
                covariance_qualified=qualified,training_observation_ids=sorted(train_ids),target_observation_ids=track['observation_ids']))
            print(case,model,'TARGET',test,'QUALIFIED',qualified,flush=True)
        write(OUT/(case+'.json'),dict(case=case,rows=rows,no_GPS_or_position_estimate_changed=True))
    write(OUT/'execution.json',dict(all_terminal=True))


if __name__=='__main__':main()
