"""Evaluate all frozen weighted-prior controls, without per-scan GPS selection."""

import csv
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from probe_ds23_weighted_priors import OUT,CONTROLS,WEIGHTS,SOURCE
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import read,sha,write

LABELS=dict(baseline="ALGO01",weighted="RX support",phase_floor3="RX support + phase floor3",
            fragment300="RX support + fragment300",receiver50="RX support + smooth50",
            combined="RX support + all three")


def run():
    protocol=read(OUT/"protocol.json")
    assert len(protocol["cases"])==20
    cases=sorted(protocol["cases"])
    rows=[]
    for case in cases:
        d=read(OUT/(case+".json"));original=read(SOURCE/case/"result.json")
        weighted=read(WEIGHTS/case/"result.json")["results"]["cross_rx_support"]
        for method in ("baseline","weighted")+CONTROLS:
            for arm in ("c0","fitted_c"):
                r=(original["arms"][arm]["record"] if method=="baseline" else
                   weighted["arms"][arm] if method=="weighted" else d["results"][method]["arms"][arm])
                valid=True if method=="baseline" else weighted["valid"] if method=="weighted" else d["results"][method]["valid"]
                gates=original["arms"][arm]["metrics"]["accepted_points"] if method=="baseline" else r["gates"]["accepted_points"]
                rows.append(dict(case=case,method=method,arm=arm,error_km=position_error(r["endpoint_latlon"]),
                                 input_points=r["active_points"],passing_points=gates,RMS_hz=r.get("RMS_hz",r.get("fit",{}).get("residual_rms_hz")),valid=valid))
    summary={}
    for method in ("baseline","weighted")+CONTROLS:
        summary[method]={arm:dict(summarize([r["error_km"] for r in rows if r["method"]==method and r["arm"]==arm]),
             valid_count=sum(r["valid"] for r in rows if r["method"]==method and r["arm"]==arm)) for arm in ("c0","fitted_c")}
    with (OUT/"comparison.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
    write(OUT/"summary.json",dict(results=summary,target_met=False,GPS_used_only_for_evaluation=True,
        no_per_scan_GPS_model_selection=True,all_20_scans_reported=True))
    fig,axes=plt.subplots(2,1,figsize=(15,8.5),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,("c0","fitted_c"),strict=True):
        for k,method in enumerate(("baseline","weighted")+CONTROLS):
            vals=[next(r["error_km"] for r in rows if r["case"]==case and r["method"]==method and r["arm"]==arm) for case in cases]
            ax.plot(range(20),vals,".-",label=LABELS[method],alpha=.8)
        ax.axhline(.5,c="crimson",ls="--",lw=1,label="0.5 km target")
        ax.set(ylabel="Position error (km)",title=arm);ax.legend(ncol=4,fontsize=8);ax.grid(alpha=.2)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    axes[-1].set_xlabel("DS23 scan")
    fig.suptitle("Frozen independent-scan prior controls · all outcomes retained")
    fig.savefig(OUT/"position_error_by_scan.png",dpi=160);plt.close(fig)
    table=["| Rule | c0 mean / median, km | Fitted-c mean / median, km | Valid pairs |",
           "|---|---:|---:|---:|"]
    for method in ("baseline","weighted")+CONTROLS:
        a,b=summary[method]["c0"],summary[method]["fitted_c"]
        table.append(f"| {LABELS[method]} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {a['valid_count']}/20 |")
    text="""# DS23: controlled priors on receiver-support weighting

**The 0.5 km mean/median target is not achieved.** Tighter fragment-offset
priors improve this 20-scan benchmark more consistently than the scan-217
combination. All outcomes, including regressions, are reported. This is not
new-location validation or the full 413-member DS23 population.

TABLE

![Position error by scan](position_error_by_scan.png)

## Controlled experiment

The base rule is the frozen [independent receiver-support weighting](../2026_10_18_ds23_family_weighting_active_support/README.md).
The four declared controls are: causal satellite-phase sigma floor3s instead
of1s; independent fragment-constant sigma300Hz instead of1000Hz; shared receiver
smooth sigma50Hz instead of200Hz; and their combination. Linear receiver drift,
cross-band terms, causal TLE mean/history, physical orbit-mode priors, broad
candidate bank, radio noise and discrete satellite/alias labels are unchanged.
The 25×25km box and regional-center initialization remain unchanged.

All controls were declared before the cohort run. Scan217 and scan45 were the
initial development probes, rather than a held-out test set. Every control uses
the same original retained observations at its first round, five phase-reference
rounds, at most48 position steps per round, and at most4 paired exclusion/refit
rounds. A failure in either c arm masks the component in both arms. Final masks
can differ between controls, so the result is a complete quality-gated policy
comparison, not a fixed-mask attribution of every gain to one prior parameter.
Histories preserve the initial common-data endpoints and subsequent exclusions.

The posterior scaling explicitly maps coefficients/precisions back to the native
design coordinates before constructing receiver states or applying gates. This
prevents a 50Hz feature design from incorrectly returning a 200Hz receiver state.
The normalized nuisance-volume and grouped-noise costs remain in the objective.
No threshold was widened to accept a more favorable location. No GLRT measurement
was corrected by its polynomial or by the supplied evaluation coordinate.

## Why scan217 alone is insufficient

The combination reaches **0.493km c0 /0.415km fitted-c** on scan217, retaining681
points that pass all original gates. However, the same combination worsens scan45
to **0.841/1.098km**. It also loses the cohort advantage of the simpler
fragment300 control. A per-scan choice using GPS would be an oracle and is not
reported as an algorithm.

An additional RF-only selection test compares all five prior models on one
common intersection mask, with identical observations, labels, alias integers,
weights and budgets. On scan217 its RF objective selects fragment300 at
**2.846/2.764km**, not the combination within0.5km. The combination costs about
29.74 more RF units at c0 on those same681 points. On scan45 the RF selector
chooses the combination, whose position is worse. Lower marginal RF loss does
not automatically identify the best geographic model in these data.
These two RF-selection probes are diagnostic; a full 20-scan RF-selection
evaluation has not yet been completed.

## Interpretation and continuing work

Receiver-independent support is useful, and a narrower fragment-offset prior
helps the mean and median here. Those changes still leave roughly kilometer
errors, and location cannot be fixed by choosing the best of this table for
each known GPS location. The ambiguity among shared receiver behavior,
transmitter frequency offsets, causal orbit errors and position remains.

Archived frame-epoch timing was also probed. It reproduces the previously
documented [negative-range relation](../2026_10_17_dsx01_iteration6/frame_phase_audit/README.md)
on some clean traces, alongside large discontinuities on others. The coordinate
has positive arrival-epoch semantics: the negative relation is **not** a sign
convention and cannot simply be negated into a pseudorange estimator. No timing
position result is claimed.

This caution is consistent with published findings that Starlink frame and
carrier clocks can differ and that frame timing has discontinuities and
beam-dependent behavior. See [Qin et al., Timing Properties](https://arxiv.org/html/2501.05302v1)
and [Qin et al., Pilots and Other Predictable Elements](https://arxiv.org/abs/2602.02627).
The local data do not identify transmitter clock control as the cause of the
observed sign or the geographic error.

Continue with independently justified timing/CFO evidence, causal orbital-prior
diagnostics and validation on untouched scans, rather than GPS-selected priors.
ALGO01 is unchanged. The successful single-scan fit does not meet the DS23 goal.

## Evidence and reproducibility

[Protocol](protocol.json) · [All results CSV](comparison.csv) ·
[Summary](summary.json) · [Execution receipts](execution.json) · [Validation](validation.json)

`tools/run_ds23_weighted_prior_controls.py` runs two bounded subprocess workers;
`tools/probe_ds23_weighted_priors.py --case DS23-0217` runs one case;
`tools/report_ds23_weighted_priors.py` evaluates after inference. Use the
repository .venv, PYTHONPATH=src:tools, OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1.
Every scan JSON preserves source/input hashes, common c-arm masks, nuisance
states, gate histories, original-data-round endpoints and final fit details.
No new RF or mutation of QNAP inputs is part of this experiment.
""".replace("TABLE","\n".join(table))
    (OUT/"README.md").write_text(text)
    write(OUT/"validation.json",dict(all_cases_present=len(cases)==20,
        all_controls_pass_final_gates=all(r['valid'] for r in rows),
        cases_with_source_hash_mismatch=[case for case in cases if read(OUT/(case+'.json'))['source_sha256']!=protocol['source_sha256']],
        comparison_rows=len(rows),no_GPS_model_selection=True,source_hash=sha(Path(__file__))))
    print('\n'.join(table),flush=True)


if __name__=="__main__":run()
