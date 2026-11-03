"""Fixed prediction audit: selected-bank visibility versus frequency support."""
import json
from pathlib import Path
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from leo.analysis.shared_scan_model import density
from leo.application.hard60_runner import HARD60_SCORE

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
ATTEMPT=HERE/'S03-early_to_late'


def support(terms,visibility,q,mask):
    visible=visibility>0
    nearest=np.min(np.where(visible,abs(terms.residual_hz),np.inf),axis=1)
    best=terms.responsibilities.argmax(1)
    associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    finite=mask&np.isfinite(nearest)
    mass=visibility@q
    quantile=lambda values:dict(zip(['minimum','q25','median','q75','maximum'],map(float,np.quantile(values,[0,.25,.5,.75,1])))) if len(values) else None
    return dict(observations=int(mask.sum()),associated=int((mask&associated).sum()),
        rows_with_any_selected_visible=int((mask&visible.any(1)).sum()),
        selected_ids_with_any_visibility=int(visible[mask].any(0).sum()) if mask.any() else 0,
        visible_q_mass=quantile(mass[mask]),nearest_visible_residual_hz=quantile(nearest[finite]),
        no_visible_selected_rows=int((mask&~visible.any(1)).sum()),
        nearest_visible_within_125_hz=int((mask&(nearest<=125)).sum()),
        nearest_visible_within_375_hz=int((mask&(nearest<=375)).sum()))


def run():
    with np.load(ATTEMPT/'held-predictions.npz') as frozen:
        p={name:frozen[name].copy() for name in frozen.files}
    with np.load(ATTEMPT/'evaluation.npz') as evaluated:
        old_associated=evaluated['associated'].copy()
    rows=[json.loads(line) for line in (REPORTS/'2026_10_16_dsx01_fast_association_losses'/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']=='S03']
    assert_array_equal(p['times_s'],[r['time_s'] for r in rows])
    terms,details=density(np.array([r['measured_cfo_hz'] for r in rows]),p['prediction_hz'],
        p['visibility_weight'],np.full(len(rows),125.),p['detection_probability'],HARD60_SCORE)
    best=terms.responsibilities.argmax(1)
    associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
    assert_array_equal(associated,old_associated)
    original=json.loads((ATTEMPT/'evaluation.json').read_text())
    assert_allclose(details['row_nll'][p['train_mask']].sum(),original['train']['conditional_cfo_nll'],atol=1e-8,rtol=0)
    train=p['train_mask'];held=p['held_mask'];vis=p['visibility_weight'];q=p['detection_probability']
    candidates=[]
    for k,number in enumerate(p['number']):
        candidates.append(dict(number=int(number),q=float(q[k]),
            total_timing_s=original['total_timing_s'][str(number)],
            visible_train_rows=int((train&(vis[:,k]>0)).sum()),visible_held_rows=int((held&(vis[:,k]>0)).sum()),
            assigned_train_rows=int((train&associated&(best==k)).sum()),assigned_held_rows=int((held&associated&(best==k)).sum()),
            mean_train_posterior=float(terms.responsibilities[train,k].mean()),
            mean_held_posterior=float(terms.responsibilities[held,k].mean())))
    bins=[]
    for start in np.arange(0,300,30):
        mask=(p['times_s']>=start)&(p['times_s']<start+30)
        bins.append(dict(start_s=float(start),end_s=float(start+30),
            train=support(terms,vis,q,mask&train),held=support(terms,vis,q,mask&held)))
    result=dict(source_id='S03',train=support(terms,vis,q,train),held=support(terms,vis,q,held),
        selected_ids=len(candidates),ids_with_assigned_train_support=sum(c['assigned_train_rows']>0 for c in candidates),
        ids_with_assigned_held_support=sum(c['assigned_held_rows']>0 for c in candidates),
        training_supported_ids_visible_on_held=sum(c['assigned_train_rows']>0 and c['visible_held_rows']>0 for c in candidates),
        candidates=candidates,time_bins=bins,
        qualification='No fit, alternative bank, timing adjustment or calibration-policy selection. '
        'Visibility means the original compact-horizon weight is positive. Frequency proximity is a model diagnostic, not a correct-identity label. '
        'Visible selected IDs do not prove the actual emitter is present in the training bank. '
        'Large frequency discrepancies can reflect missing correct satellites, timing or calibration extrapolation; these causes are not identified separately here.')
    with (ATTEMPT/'held_diagnostics.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ['train','held','selected_ids','ids_with_assigned_train_support','ids_with_assigned_held_support','training_supported_ids_visible_on_held']}),flush=True)


if __name__=='__main__':run()
