"""Attribute previously sealed detector outputs to acquisition and GLRT steps."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-cached-ambiguity-r01/iq')
DEPLOYED = Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = OLD/'results.json'
    assert sha(path) == '5ebba36c07be8d3f79884946424322a471099693bf4b7794653fb67bdee63d42'
    data = json.loads(path.read_text())
    rows = []
    for slot in data['slots']:
        assert slot['status'] == 'complete'
        if not slot['sources']:
            continue
        s = slot['sources'][0]
        reference = s['cfo_hz'] + .01*s['rate_hz_s']
        for receiver in slot['receivers']:
            winner = receiver['summary']['highest_margin_accepted']
            assert winner is not None
            acquired = winner['acquired_cfo_hz']
            residual = winner['fractional_residual_cfo_hz']
            final = winner['fractional_tracking_cfo_hz']
            assert abs(acquired+residual-final) < 1e-8
            rows.append(dict(scenario=slot['scenario'], seed=slot['seed'],
                receiver_id=receiver['receiver_id'], candidate_rank=winner['candidate_rank'],
                reference_midpoint_hz=reference, acquired_CFO_hz=acquired,
                acquired_minus_reference_hz=acquired-reference,
                fractional_GLRT_residual_hz=residual, final_CFO_hz=final,
                final_minus_reference_hz=final-reference,
                GLRT_grid_step_hz=1/(512*4.4e-6),
                residual_grid_steps=residual*512*4.4e-6,
                fractional_margin=winner['fractional_margin']))
    with (HERE/'stage_attribution.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    names = list(dict.fromkeys(r['scenario'] for r in rows))
    summaries=[]
    for name in names:
        subset=[r for r in rows if r['scenario']==name]
        summaries.append(dict(scenario=name, count=len(subset),
            acquired_mean_difference_hz=float(np.mean([r['acquired_minus_reference_hz'] for r in subset])),
            GLRT_mean_increment_hz=float(np.mean([r['fractional_GLRT_residual_hz'] for r in subset])),
            final_mean_difference_hz=float(np.mean([r['final_minus_reference_hz'] for r in subset]))))
    fig,ax=plt.subplots(figsize=(11.8,5.8))
    x=np.arange(len(summaries))
    acq=np.array([r['acquired_mean_difference_hz'] for r in summaries])
    incr=np.array([r['GLRT_mean_increment_hz'] for r in summaries])
    ax.bar(x,acq,color='#3c78a8',label='Acquisition minus generated midpoint')
    ax.bar(x,incr,bottom=acq,color='#d47a3a',label='Additional fractional GLRT frequency step')
    ax.scatter(x,acq+incr,color='black',marker='D',s=35,zorder=4,label='Final CFO difference')
    for i,v in enumerate(acq+incr):
        ax.annotate(f'{v:+.2f}',(i,v),xytext=(0,9 if v>=0 else -16),
                    textcoords='offset points',ha='center',fontsize=9)
    ax.axhline(0,color='black',linewidth=.8)
    ax.set_xticks(x,['Strong','Reduced\namplitude','Same epoch\n500 Hz apart',
        'Same epoch\n3,000 Hz apart','Separate epoch\n500 Hz apart',
        'Separate epoch\n3,000 Hz apart','Chirp\nvs midpoint'])
    ax.set_ylabel('Frequency difference / increment (Hz)')
    ax.set_ylim(-540,150)
    ax.grid(axis='y',alpha=.2)
    ax.legend(loc='lower right',fontsize=9)
    fig.suptitle('Where the prior synthetic CFO displacement entered',fontsize=14)
    fig.text(.5,.015,'Saved outputs only; four outputs per condition. Known waveform mismatch. No new detector call, track test or field-bias claim.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.95))
    fig.savefig(HERE/'stage_attribution.png',dpi=180)
    fig.savefig(HERE/'stage_attribution.pdf')
    plt.close(fig)
    summary=dict(source=str(path),source_sha256=sha(path), rows=len(rows),
        summaries=summaries,new_detector_calls=0,new_synthetic_inputs=0,
        code_review={str(p):sha(p) for p in [
            DEPLOYED/'leo/scanner/fast_scan_analysis.py',
            DEPLOYED/'leo/analysis/starlink/fast_scan_scores.py',
            DEPLOYED/'leo/analysis/starlink/fast_scan_fractional.py',
            DEPLOYED/'leo/analysis/starlink/templates.py']},
        scorer_symbols=list(range(2,66)),FFT_grid_size=512,
        grid_spacing_hz=1/(512*4.4e-6),selected_symbol_duration_s=64*4.4e-6,
        independent_validation=False,known_template_mismatch=True)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    files=[p for p in HERE.iterdir() if p.is_file() and p.name!='seal.json']
    (HERE/'seal.json').write_text(json.dumps({p.name:sha(p) for p in sorted(files)},indent=2)+'\n')
    print(json.dumps(dict(rows=len(rows),summaries=summaries,new_detector_calls=0)))


if __name__=='__main__':
    main()
