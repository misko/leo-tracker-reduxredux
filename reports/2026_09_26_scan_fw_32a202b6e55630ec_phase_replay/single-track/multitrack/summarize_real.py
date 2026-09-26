"""Render final real-data evidence with matched circular scores."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def main():
    data=json.loads((HERE/'metrics.json').read_text())['results']
    keys=['simultaneous_donor_frozen_difference','target_only_linear_frequency_forecast','target_only_constant_phase','wrong_time_donor_control']
    labels=['Shared-mode transfer','Target-only linear','Target-only constant','Wrong-time donor']
    scores=[np.array([r[k]['rmse_degrees'] for r in data]) for k in keys]
    medians=[float(np.median(s)) for s in scores]
    fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
    bars=ax.bar(labels,medians,color=['#368985','#748a9d','#9babb8','#bd8b5f'])
    ax.bar_label(bars,labels=[f'{m:.1f}°' for m in medians],padding=4)
    ax.axhline(180/np.sqrt(3),color='gray',ls='--',label='Uniform-angle RMS scale (104°), not a significance test')
    ax.set(ylim=(0,140),ylabel='Median held wrapped phase RMS (degrees)',title='Real recording · 8 visits · 2 simultaneous candidate modes per visit')
    ax.tick_params(axis='x',labelrotation=10);ax.legend(fontsize=8)
    fig.supxlabel('First 28 ms fit; later 91 ms held. 16 directed scores share 8 visits and are not independent replicates.',fontsize=9)
    for extension in ('png','svg'):fig.savefig(HERE/f'comparison.{extension}',dpi=170)
    (HERE/'SUMMARY.md').write_text('''# Real adaptive-scan shared-phase prototype

**The test ran on recorded IQ, not synthetic replacement data. It did not establish useful separation of shared LNB/LO phase or preserved geometric tracks.**

SOL implemented data extraction and the conditional model; root independently audited support, corrected the initial unwrapped scoring, and tested adjacent-visit transfer. The earlier unwrapped-error figures are superseded by these wrapped results.

![Real-data comparison](comparison.png)

| Method | Median held wrapped RMS |
| --- | ---: |
| Current donor mode + frozen target-minus-donor line | 102.33° |
| Target-only linear phase | 103.78° |
| Target-only constant phase | 110.52° |
| Wrong-time donor with the same frozen relation | 106.99° |

The shared-mode method wins 9/16 directed comparisons against the linear baseline and 9/16 against wrong-time control. These are two directions on each of eight visits, not 16 independent trials. All 208 held target-window predictions remain in the denominator. There is no compelling common-term recovery in this bounded comparison.

## Actual data and selection

The full 2,214-visit acquisition census contains 18 visits admitted by the existing phase-blind two-mode rule. Eight were selected using metadata:14,52,73,74,1074,1711,1734,1735. The original frozen128-visit cohort had included only1074/1711. Each selected visit yields17 non-overlapping7ms windows per mode:272 observations total,64 training and208 evaluation. The first4 windows (28ms) fit the relation; the last13 (91ms) are held. Each window contains4–5 pilot frames. Median in-window fitted resultant is0.906, which is not itself forward-prediction evidence.

The two modes have different admitted canonical frequencies and frame epochs. Duplicate aliases are grouped by the existing admission rule, but separate emitter identity is not proved. Both receivers' capture chunk hashes are verified by the loader. [Support census](support-audit.json), [extraction metadata](data/metadata.json), [real observations](data/observations.csv), and [independent input audit](validation.json) are retained.

## What the model tests

Each mode keeps its own template timing but uses the same strongest-primary RX frequency authority and common physical midpoint. Extracted phase is restored to that common coordinate before comparison. The model fits wrapped target-minus-donor phase on training windows only. It predicts later target phase using the donor's simultaneous observation and the frozen difference. It does not use later target phase to fit an offset. This is simultaneous correction, not future-only forecasting.

Unknown cycle branches require wrapped scores. The corrected implementation is invariant to adding integer2π turns independently to input samples; training alone chooses any branch needed for the difference slope. Wrong-time control shifts the donor while keeping calibration unchanged. No source phase is flattened by fitting a held-time correction.

The general common-polynomial + per-mode-polynomial implementation also exposes its p+1-dimensional ambiguity. Assigning their mean to the common term is a coordinate convention, not identification of an LNB phase. No satellite-specific orbit fit was attempted because the candidate identities/directions and baseline length are not established.

## Adjacent-visit test

Visits73 and74 share CH4/target7 and are separated by a375µs capture gap, without an intervening different target. Their two candidate frequencies change by−430 and−381Hz; frame-lattice mismatches are5.82 and1.51samples. This makes continuity a testable candidate association, not an identity proof.

Fitting the mode difference on all17 windows of visit73 and applying it unchanged to visit74 gives **69.12° RMS** for a linear model, versus101.68° for a circular constant and115.35° for a quadratic. All17 visit74 windows are held and no new phase offset is fitted. Current visit74 donor phase is still required. This is too weak to qualify preserved geometric phase and is **not a cross-retune success**.

![Adjacent-visit transfer](revisit-transfer.png)

Visits1734/1735 have different targets and are not treated as repeated tracks. No unsupported connection across scan retunes is manufactured. [Adjacent test script](revisit_transfer.py) and [results](revisit-results.json) are included.

## Interpretation and reproducibility

The hypothesis that all signals share an instrumental contribution remains physically plausible. This experiment does not validate a usable estimate of it. Uncertain mode association, template leakage, mode-dependent propagation, local estimator errors and sparse phase sampling remain possible explanations; the 79° baseline axis alone does not resolve them.

Reproduce with data/build_observations.py, run.py, validate_real.py, revisit_transfer.py, then summarize_real.py under the pinned scientific runtime and src PYTHONPATH documented in the parent report. No RF collection or production change was made. [SOL model report](REPORT.md), [full metrics](metrics.json), and [combined test receipt](tests.xml) are included.
''')

if __name__=='__main__':main()
