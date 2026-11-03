"""Diagnose N08's optimizer stall without altering visibility or refitting data."""
import json
import numpy as np
from post_scan_tle_localization import OUT, load_variant, make_objective
from timing_bound_comparison import digest
from subset_positions import serial


def inspect_step(obj, vector, index, scaled_step):
    trial = np.asarray(vector).copy(); trial[index] += scaled_step*obj.scale[index]
    score, gradient = obj.evaluate(vector)
    predicted, visible = obj.base.predict(vector[:obj.size])
    before = obj.likelihood.last_result['row_association_probability'].copy()
    next_score, _ = obj.evaluate(trial)
    next_predicted, next_visible = obj.base.predict(trial[:obj.size])
    after = obj.likelihood.last_result['row_association_probability'].copy()
    # Counterfactual evaluation ONLY: preserve old gate to isolate its jump.
    held = obj.likelihood.evaluate(next_predicted, visible, sigma_hz=obj.base.sigma_hz)
    held_score = -held['total_log_likelihood'] + obj.base.penalty(trial[:obj.size])[0]
    flips = []
    for i, j in np.argwhere(visible != next_visible):
        data = obj.base.data
        frequency = predicted[i,j] + (obj.features@vector[obj.size:])[i]
        residual = (data.measured[i]-frequency+obj.likelihood.alias_hz/2)%obj.likelihood.alias_hz-obj.likelihood.alias_hz/2
        flips.append(dict(row=int(i), time_s=float(data.times[i]), receiver=int(data.receiver[i]),
            channel=int(data.channel[i]), satellite=int(data.numbers[j]), original_owner=int(data.owners[i]),
            visible_before=bool(visible[i,j]), visible_after=bool(next_visible[i,j]), residual_hz=float(residual),
            probability_before=float(before[i,j]), probability_after=float(after[i,j])))
    return dict(index=index, scaled_step=scaled_step, physical_step=float(trial[index]-vector[index]),
        actual_score_change=next_score-score, local_linear_prediction=gradient[index]*scaled_step*obj.scale[index],
        frozen_gate_score_change=held_score-score, visibility_jump=next_score-held_score, flips=flips)


def main():
    source=OUT/'polished/N08/fitted-c-original.json'; result=json.loads(source.read_text())
    data,meta,_,_=load_variant('N08','original'); obj=make_objective(data,meta,'fitted-c')
    vector=np.asarray(result['best']['vector'])
    steps=[inspect_step(obj,vector,16,step) for step in (1e-5,1e-6,1e-7)]
    assert all(len(r['flips']) == 1 and r['flips'][0]['satellite'] == 62493 for r in steps)
    assert all(r['flips'][0]['probability_before'] == r['flips'][0]['probability_after'] == 0 for r in steps)
    assert all(r['visibility_jump'] > .03 and r['frozen_gate_score_change'] < 0 for r in steps)
    report=dict(scope=__doc__, source_sha256=digest(source), scan='N08', arm='fitted-c', variant='original',
        steps=steps, note='Hard horizon visibility changes both missed-detection and nonempty-window normalization terms. '
        'This is a nonsmooth model feature, not a wrong analytic derivative within a fixed visibility region. '
        'Explains this stall; does not establish the cause of the overall position bias. No production gate change made.')
    (OUT/'visibility-step-audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
