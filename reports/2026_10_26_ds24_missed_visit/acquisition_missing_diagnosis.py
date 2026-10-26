"""Posthoc nomination diagnosis; no target or scoring-policy changes."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    rows, sources = [], {}
    for path in sorted((ROOT/'timing/outcomes').glob('DS*.json.gz')):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        with gzip.open(path, 'rt') as handle:
            document = json.load(handle)
        for window in document['rows']:
            for cell in window.get('cells', []):
                found = cell['result'].get('search')
                originals = cell['original_fullwindow'].get('candidates', [])
                if not found or not found['evaluation']['admitted'] or any(c['passed_fractional_margin_gate'] for c in originals):
                    continue
                frequency = found['confirmation']['tracking_cfo_hz']
                epoch = found['confirmation']['epoch_samples']
                period = 10_000_000/750
                comparisons = []
                for original in originals:
                    other = original['integer_epoch_sample']+original['fractional_epoch_offset_samples']
                    timing = (other-epoch+period/2)%period-period/2
                    comparisons.append(dict(rank=original['candidate_rank'],
                        timing_difference_samples=timing,
                        CFO_difference_hz=original['fractional_tracking_cfo_hz']-frequency,
                        margin=original['fractional_margin']))
                rows.append(dict(prediction_id=cell['prediction_id'], case=window['case'],
                    channel=window['channel'], native_receiver=cell['receiver_id'],
                    original_proposals=len(originals), confirmation_margin=found['confirmation']['margin'],
                    best_original_margin=max((c['margin'] for c in comparisons), default=None),
                    nearest_timing_samples=min((abs(c['timing_difference_samples']) for c in comparisons), default=None),
                    nearest_CFO_hz=min((abs(c['CFO_difference_hz']) for c in comparisons), default=None),
                    has_joint_proposal_within2samples500Hz=any(abs(c['timing_difference_samples'])<=2 and abs(c['CFO_difference_hz'])<=500 for c in comparisons),
                    original_comparisons=comparisons))
    summary = dict(new_owners=len(rows),
        no_original_proposals=sum(r['original_proposals']==0 for r in rows),
        any_original_timing_within2samples=sum(r['nearest_timing_samples'] is not None and r['nearest_timing_samples']<=2 for r in rows),
        any_original_CFO_within500Hz=sum(r['nearest_CFO_hz'] is not None and r['nearest_CFO_hz']<=500 for r in rows),
        joint_original_within2samples500Hz=sum(r['has_joint_proposal_within2samples500Hz'] for r in rows),
        median_new_confirmation_margin=float(np.median([r['confirmation_margin'] for r in rows])))
    result=dict(schema='posthoc-original-acquisition-proposal-diagnosis/v1', summary=summary,
        rows=rows, source_hashes=sources, parameters_changed=False,
        limitations=['New confirmed timing/CFO is an evaluation reference, not external satellite truth.',
            'Timing differences are circular over a native frame; CFO differences are raw, without an assumed physical alias correction.',
            'Original margins use full support while new margins use confirmation support; they are labeled exposure contexts.'])
    (ROOT/'acquisition_missing_diagnosis.json').write_text(json.dumps(result, indent=2)+'\n')
    fig, axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for row in rows:
        if row['best_original_margin'] is not None:
            axes[0].scatter(row['best_original_margin'],row['confirmation_margin'],
                color='#286b9b' if row['channel']>=5 else '#aaa',alpha=.8)
    axes[0].axvline(.025,color='k',ls='--',lw=1);axes[0].axhline(.025,color='k',ls='--',lw=1)
    axes[0].set(xlabel='Best original full-window margin',ylabel='New confirmation margin',
                title='New detections often have strong pilot support')
    values=np.sort([r['nearest_timing_samples'] for r in rows if r['nearest_timing_samples'] is not None])
    axes[1].step(values,np.arange(1,len(values)+1)/len(values),where='post')
    axes[1].axvline(2,color='k',ls='--',lw=1)
    axes[1].set(xscale='log',xlabel='Nearest original timing proposal error (samples)',
                ylabel='Fraction of new owners',title='Did original acquisition nominate this arrival time?')
    fig.suptitle('Posthoc diagnosis of 30 originally absent detections; no policy retuning')
    for extension in ['png','pdf']:
        fig.savefig(ROOT/f'acquisition_missing_diagnosis.{extension}',dpi=180)
    plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
