"""Summarize the bounded SOL experiments without conflating forecast horizons."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def main():
    tracker=json.loads((HERE/'tracker/tracker-results.json').read_text())
    rows={r['model']:r for r in tracker['aggregates']}
    groups=[(['glrt_only_constant_phase','constant_frequency','smooth_frequency_rate'],['GLRT only','Constant frequency','Frequency + rate'],'Frozen first 20 ms → later ~100 ms'),
            (['previous_phase','two_frame_increment','cautious_robust'],['Previous phase','Previous increment','Robust tracker'],'Past frames → next frame (~1.333 ms)')]
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for ax,(models,labels,title) in zip(axes,groups):
        values=[rows[m]['all_held_failure_inclusive_rmse_deg'] for m in models]
        bars=ax.bar(labels,values,color=['#758da0','#398786','#b18b61'])
        ax.bar_label(bars,labels=[f'{v:.1f}°' for v in values],padding=4)
        ax.set(ylim=(0,135),ylabel='Wrapped prediction RMS (degrees)',title=title)
        ax.tick_params(axis='x',labelrotation=12)
    fig.suptitle('Held odd-tone prediction · five dwells · 371 later frames',fontsize=15)
    fig.supxlabel('Different horizons: compare within panels. Robust tracker: six missing forecasts charged 180°; conditional RMS 46.6°.',fontsize=9)
    for extension in ('png','svg'):fig.savefig(HERE/f'comparison.{extension}',dpi=180)
    text='''# SOL phase-recovery improvements: implementation and tests

All three delegated SOL workstreams completed on the same five GLRT-selected dwells (259–263). The shared cache contains 445 frames: 70 early training frames, 371 later frames, and four split-crossing exclusions. Production code and recording data are unchanged.

**The best tested short-horizon predictor is the simple previous-frame phase increment. None of the tested models establishes a stable 100 ms phase forecast or geometric satellite phase.**

![Comparison of held predictions](comparison.png)

| Approach | Validation horizon | Wrapped phase RMS | Outcome |
| --- | --- | ---: | --- |
'''
    descriptions={
        'glrt_only_constant_phase':('GLRT correction + fixed training phase','up to ~100 ms','Baseline; phase continues moving.'),
        'constant_frequency':('Joint differential constant frequency','up to ~100 ms','Improves on GLRT baseline, but remains weak.'),
        'smooth_frequency_rate':('Joint differential frequency + rate','up to ~100 ms','Worse than constant frequency; extra curvature does not generalize.'),
        'previous_phase':('Previous even-tone phase','~1.333 ms','Simple causal baseline.'),
        'two_frame_increment':('Previous two-frame phase increment','~1.333 ms','Best tested next-frame predictor; no long-horizon claim.'),
        'cautious_robust':('Robust recent-history tracker','~1.333 ms','46.55° on 365 forecasts; six missing forecasts penalized at 180°.')}
    for model in ('glrt_only_constant_phase','constant_frequency','smooth_frequency_rate','previous_phase','two_frame_increment','cautious_robust'):
        label,horizon,outcome=descriptions[model]
        text+=f"| {label} | {horizon} | {rows[model]['all_held_failure_inclusive_rmse_deg']:.2f}° | {outcome} |\n"
    text+='''
Each differential tracker fits even-index tones and scores odd-index tones without fitting their held phase offsets. Frozen forecasts use only the first 20 ms. Rolling forecasts are issued before incorporating the current frame; current jumps therefore count as prediction errors. Short-horizon scores do not qualify prediction across dwell gaps. The 180° missing-forecast penalty is an explicit scoring convention, not a measured error.

## Response and delay result

Training-only fixed per-tone normalization changes held summed phase by only **0.19–0.77° RMS**. Corrected tone agreement is **0.9735–0.9817**. Fixed relative tone response therefore does not explain the larger common phase trajectory. Tone-slope delay estimates range from −9.88 to +4.80 ns but are ambiguous modulo 4.2667 μs; they are not a physical baseline calibration.

[Response report and figure](response/REPORT.md) · [tracker implementation, metrics and predictions](tracker/REPORT.md)

## Independent review

The 16-tap fractional interpolation support does not change the split; the nearest safe margin is 3.20 μs. Root review caught and corrected current-observation gating of rolling forecasts. The independent validator also caught and corrected missing forecast-denominator serialization. The final results retain rejected and missing cases.

The current pilot preprocessing estimates a shared per-frame residual from all RX0 tones. Even/odd validation therefore holds out differential phase from the tracker, but is not a fully independent raw-frequency holdout. The comparison is descriptive on this selected segment; no held-data hyperparameter search was performed. Uncertainty estimates based on recent residual scatter are diagnostic, not established calibrated confidence intervals.

The capture identifies one dual-channel Pluto and a configured LNB frequency. It does not establish antenna baseline, shared LNB/LO topology, cable calibration, satellite identity or look direction. Those quantities are needed to decide how slow geometric phase should be. Existing weak broadband delay fits cannot supply them.

[Independent validation report](validation/REPORT.md) · [frozen cache metadata](pilot-cache.json) · [execution scope](EXECUTION.md)

## Practical next step

Keep the simple previous-increment predictor as the baseline. Before adding tracker complexity, repeat this fixed comparison on other preselected segments and obtain the actual antenna/LO/clock configuration. A smooth-looking corrected trace alone should not be treated as recovered satellite geometry. Implementation and regression tests are retained; see [combined test receipt](tests.xml).
'''
    (HERE/'REPORT.md').write_text(text)

if __name__=='__main__':main()
