"""Read-only diagnostic of a saved N08 hard-horizon score discontinuity.

No optimization or change to fitted models. Freeze the saved visibility mask only
in the diagnostic curve, to isolate the source of the score jump. This frozen
mask is not proposed here as a scientifically validated localization model.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import position_interaction_study as s


def normalizer(log_empty):
    return log_empty-np.log(-np.expm1(log_empty))


def main():
    path=s.OUT/'initial'/'N08-fitted-c-GT.json'
    record=json.loads(path.read_text())
    data,saved,*_=s.inputs('N08')
    obj=s.objective(data,saved,'fitted-c','GT')
    v=np.array(record['best']['vector'])
    base,g=obj.evaluate(v)
    prediction,mask=obj.base.predict(v[:obj.size])
    offsets=np.r_[np.linspace(-.002,-.000001,60),0.,np.linspace(.000001,.002,60)]
    rows=[]
    for step in offsets:
        trial=v.copy();trial[6]+=step
        score,_=obj.evaluate(trial)
        pred,visible=obj.base.predict(trial[:obj.size])
        actual=obj.likelihood.last_result['window_log_likelihood'].copy()
        fixed=obj.likelihood.evaluate(pred,mask,sigma_hz=obj.base.sigma_hz)
        fixed_score=-fixed['total_log_likelihood']+obj.base.penalty(trial[:obj.size])[0]+obj.extra_penalty(trial)[0]
        rows.append(dict(timing_offset_s=float(step),score_delta=float(score-base),
            frozen_mask_score_delta=float(fixed_score-base),
            smooth_gradient_prediction=float(g[6]*step),visibility_flips=int(np.sum(visible!=mask))))
    # Resolve the exact affected observation/satellite and the jump's cause.
    epsilon=1e-8
    left,right=v.copy(),v.copy();left[6]-=epsilon;right[6]+=epsilon
    jl,_=obj.evaluate(left);ll=obj.likelihood.last_result['window_log_likelihood'].copy()
    pl,vl=obj.base.predict(left[:obj.size])
    jr,_=obj.evaluate(right);lr=obj.likelihood.last_result['window_log_likelihood'].copy()
    pr,vr=obj.base.predict(right[:obj.size])
    flips=[]
    for i,j in np.argwhere(vl!=vr):
        residual=(data.measured[i]-pr[i,j]-obj.features[i]@v[obj.size:]+s.old.ALIAS/2)%s.old.ALIAS-s.old.ALIAS/2
        q=obj.likelihood.detection_probability
        el=-2.+int(vl[i].sum())*np.log1p(-q)
        er=-2.+int(vr[i].sum())*np.log1p(-q)
        flips.append(dict(row=int(i),original_row=int(data.original_rows[i]),norad=int(data.numbers[j]),
            original_owner=int(data.owners[i]),time_s=float(data.times[i]),rx=int(data.receiver[i]),
            channel=int(data.channel[i]),residual_hz=float(residual),
            visible_left=bool(vl[i,j]),visible_right=bool(vr[i,j]),
            row_weight=float(obj.likelihood.weights[i]),
            weighted_observation_nll_jump=float(-obj.likelihood.weights[i]*(lr[i]-ll[i])),
            visibility_normalizer_only_jump=float(-obj.likelihood.weights[i]*(normalizer(er)-normalizer(el)))))
    report=dict(scope=__doc__,source=str(path),source_sha256=s.old.previous.digest(path),
        saved_kkt=record['kkt'],epsilon_s=epsilon,score_jump=jr-jl,
        analytic_common_timing_gradient=float(g[6]),
        finite_difference_common_timing_gradient=float((jr-jl)/(2*epsilon)),flips=flips,curve=rows,
        visibility_rule='prediction_jacobian.py: direction dot local-up >= 0 (geometric horizon)',
        interpretation='Hard visible-count change enters the empty-set conditioning normalizer even when frequency support for that satellite is effectively zero. Smooth gradients hold the boolean gate fixed.')
    target=s.OUT/'visibility-diagnostic';target.mkdir(exist_ok=True)
    if (target/'audit.json').exists():
        previous=json.loads((target/'audit.json').read_text())
        assert previous['source_sha256']==report['source_sha256']
        np.testing.assert_allclose(previous['score_jump'],report['score_jump'],atol=1e-9)
    else:s.old.previous.save(target/'audit.json',report)
    s.old.csv_write(target/'curve.csv',rows)
    fig,axes=plt.subplots(1,2,figsize=(14,5.2))
    x=np.array([r['timing_offset_s'] for r in rows])*1000
    axes[0].plot(x,[r['score_delta'] for r in rows],'.-',color='#D55E00',label='Actual score: moving hard horizon')
    axes[0].plot(x,[r['frozen_mask_score_delta'] for r in rows],color='#0072B2',label='Diagnostic: saved visibility held fixed')
    axes[0].plot(x,[r['smooth_gradient_prediction'] for r in rows],'--',color='.3',label='Analytic tangent')
    axes[0].set_xlabel('Common timing perturbation (ms)');axes[0].set_ylabel('Change in negative log score')
    axes[0].set_xlim(-.2,.2);axes[0].set_ylim(-.003,.052)
    axes[0].set_title('N08 · time-balanced Gaussian · saved unconverged fit')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    f=flips[0]
    axes[1].axis('off')
    note=(f"One horizon flag changes\n\nNORAD {f['norad']} · RX{f['rx']} · CH{f['channel']} · t = {f['time_s']:.3f} s\n"
          f"This window's original satellite: {f['original_owner']}\n"
          f"Residual to the horizon satellite: {f['residual_hz']/1000:.1f} kHz\n\n"
          f"Score jump: {jr-jl:.6f} NLL\n"
          f"Visibility-normalizer contribution: {f['visibility_normalizer_only_jump']:.6f}\n\n"
          "The jump persists as the perturbation approaches zero.\n"
          "A smooth gradient cannot describe this discontinuity.\n"
          "This explains a stalled smooth convergence check,\n"
          "not the overall kilometer-scale position bias.")
    axes[1].text(.02,.93,note,va='top',fontsize=11,linespacing=1.6)
    fig.suptitle('A concrete optimizer obstacle: the hard visibility gate',fontsize=16)
    fig.text(.5,.02,'No refit and no model replacement. Frozen visibility is used only to isolate the jump; all production results remain unchanged.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.92]);fig.savefig(target/'score-jump.png',dpi=170);plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k!='curve'},indent=2))


if __name__=='__main__':main()
