"""Evaluation-only report for frozen independent-scan family weighting."""

import csv
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from evaluate_ds23_family_weighting import OUT, METHODS, SOURCE
from report_algo01_ds23_sample import position_error, summarize
from run_algo01_ds23_sample import read, sha, write

LABELS={"baseline":"ALGO01","cross_rx_support":"RX support",
        "family_cap50":"Family cap 50","cross_rx_cap100":"RX support × cap 100"}


def run():
    protocol=read(OUT/"protocol.json")
    assert len(protocol["cases"])==20
    rows=[];per_scan={};summary={}
    for case in sorted(protocol["cases"]):
        d=read(OUT/case/"result.json")
        baseline=read(SOURCE/case/"result.json")
        per_scan[case]={}
        for method in ("baseline",)+METHODS:
            per_scan[case][method]={}
            for arm in ("c0","fitted_c"):
                result=(baseline["arms"][arm]["record"] if method=="baseline" else d["results"][method]["arms"][arm])
                xy=result["endpoint_east_north_km"]
                latlon=result["endpoint_latlon"]
                error=position_error(latlon)
                gates=(baseline["arms"][arm]["metrics"]["accepted_points"] if method=="baseline" else result["gates"]["accepted_points"])
                valid=True if method=="baseline" else d["results"][method]["valid"]
                rows.append(dict(case=case,method=method,arm=arm,error_km=error,
                    east_km=xy[0],north_km=xy[1],calibration_points=result.get("active_points",gates),
                    passing_points=gates,RMS_hz=result.get("RMS_hz",result.get("fit",{}).get("residual_rms_hz")),valid=valid))
                per_scan[case][method][arm]=error
    for method in ("baseline",)+METHODS:
        summary[method]={}
        for arm in ("c0","fitted_c"):
            rr=[r for r in rows if r["method"]==method and r["arm"]==arm]
            values=[r["error_km"] for r in rr]
            changes=np.array([per_scan[r["case"]][method][arm]-per_scan[r["case"]]["baseline"][arm] for r in rr])
            valid=[r for r in rr if r["valid"]]
            summary[method][arm]=dict(summarize(values),valid_count=len(valid),
                improved=int((changes<-.001).sum()),worsened=int((changes>.001).sum()),
                no_dropouts=True,mean_passing_points=float(np.mean([r["passing_points"] for r in rr])),
                excluding_development_217=summarize([r["error_km"] for r in rr if r["case"]!="DS23-0217"]))
    with (OUT/"comparison.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
    write(OUT/"summary.json",dict(results=summary,reference_only_used_for_evaluation=True,
        all_20_cases_reported=True,development_case="DS23-0217",population_is_20_not_full_DS23=True,
        target_mean_and_median_km=.5,target_met=False))
    cases=sorted(per_scan)
    fig,axes=plt.subplots(2,1,figsize=(15,8.5),sharex=True,constrained_layout=True)
    offsets=np.linspace(-.27,.27,4)
    for ax,arm in zip(axes,("c0","fitted_c"),strict=True):
        for offset,method in zip(offsets,("baseline",)+METHODS,strict=True):
            ax.bar(np.arange(20)+offset,[per_scan[c][method][arm] for c in cases],width=.17,label=LABELS[method])
        ax.axhline(.5,color="crimson",ls="--",lw=1,label="0.5 km target")
        ax.set(ylabel="Position error (km)",title=arm);ax.grid(axis="y",alpha=.2)
        ax.legend(ncol=5,fontsize=9)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    axes[-1].set_xlabel("DS23 scan (original sealed 20-scan sample)")
    fig.suptitle("Independent scans · preset family weights · matched c pairs · unchanged causal inputs")
    fig.savefig(OUT/"position_error_by_scan.png",dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5.5),constrained_layout=True)
    for ax,arm in zip(axes,("c0","fitted_c"),strict=True):
        for method in METHODS:
            ax.scatter([per_scan[c]["baseline"][arm] for c in cases],
                       [per_scan[c][method][arm] for c in cases],s=35,label=LABELS[method])
        ax.plot([0,5],[0,5],"k--",lw=1)
        ax.set(xlabel="ALGO01 error (km)",ylabel="Prototype error (km)",title=arm,xlim=(0,5),ylim=(0,5))
        ax.legend(fontsize=9);ax.grid(alpha=.2)
    fig.suptitle("Below the diagonal improves · all scans retained")
    fig.savefig(OUT/"paired_accuracy.png",dpi=160);plt.close(fig)
    table=["| Rule | c0 mean / median, km | Fitted-c mean / median, km | Valid scans |",
           "|---|---:|---:|---:|"]
    for method in ("baseline",)+METHODS:
        a,b=summary[method]["c0"],summary[method]["fitted_c"]
        table.append(f"| {LABELS[method]} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {a['valid_count']} / 20 |")
    body="""# DS23: frozen family-weighting benchmark

The independent receiver-support rule improves median error on the original
20-scan sample, but **neither mean nor median reaches the 0.5 km target**.
All scans, including regressions and development scan 217, are retained.
These are development results, not validation on new locations or all 413 DS23
recordings. [ALGO01](../ALGO01/README.md) remains the baseline specification.

TABLE

![Position errors by scan](position_error_by_scan.png)

## Prespecified rules and controls

Use the same final original ALGO01 identities, aliases, qualified observations,
causal latest/previous TLE inputs, receiver/orbit priors, radio-noise law and
25×25 km box. Each fit starts at the regional center, with five phase-reference
rounds and at most48 Gauss–Newton steps per round. The fitted-c arm uses the
same mask, labels, aliases and likelihood powers as its c0 partner.

The RF-conditional uniqueness proxy screens every satellite in the original
causal bank at the RF-derived endpoint and four ±2 km axial perturbations.
No GPS position is used. Only original **retained** points contribute confidence,
family sizes or independent owner votes. Masked/rejected observations do not
create cross-receiver support. The original nuisance design is still retained
under masks to preserve the controlled ALGO01 prior-support convention.

RX support powers are 1 for a family observed by both receivers, 0.6 for other
families supported by at least two distinct receiver/channel combinations with
conditional uniqueness≥0.95, and 0.2 otherwise. Powers never exceed1. Family
cap50 uses min(1,50/N_family); the combined control multiplies receiver support
by min(1,100/N_family). These rules were frozen before reading cohort outcomes;
they are generalized likelihoods, not calibrated probability weights.

If either arm fails an original residual, alias, visibility or independent-owner
gate, its failed component is masked in **both** arms and both are cold-refit.
There are at most four monotone gate rounds. This is an exclusion/weighting
prototype, not a new association search or a claim that excluded points are
noise. No linear/short fragment determines calibration. Reassociation and
salvage are not rerun after this experiment's additional exclusions.

![Paired changes](paired_accuracy.png)

## Interpretation and next step

The signal is independent family replication, not simply giving more weight to
a low-RMS or conditionally unique identity. Family-size capping alone does not
improve mean error. The receiver-support rule improves the median more than
the mean; individual failures remain. The [scan-217 investigation](../2026_10_18_algo01_0217_improvements/README.md)
shows that some of its gain is weighting and some is quality-gated removal.

Do not select different rules per scan using GPS, shift endpoints toward the
known site, drop regressions from aggregate results, or infer accuracy from a
lower frequency objective. The reference coordinate is used only here for
evaluation, with the same unverified assumption that it applies to every scan
in the sample. Fixed height remains0m.

Continue with controlled physical-prior and timing/RF diagnostics. Any candidate
default must then be frozen and evaluated on previously untouched DS23 members.
The original 20-scan results and ALGO01 remain unchanged.

## Evidence and reproduction

[Summary](summary.json) · [All scan/arm results](comparison.csv) ·
[Protocol](protocol.json) · [Execution receipts](execution.json) ·
[Validation](validation.json)

Inference: `tools/evaluate_ds23_family_weighting.py --workers 2`.
Reporting: `tools/report_ds23_family_weighting.py`.
Use `.venv/bin/python`, PYTHONPATH=src:tools, OPENBLAS_NUM_THREADS=1 and
OMP_NUM_THREADS=1. Every scan directory stores raw fit/phase/gate histories,
weights, masks, confidence proxies and input/source hashes. No new RF was
collected; all radio inputs are read-only archived authorities.

An initial interrupted trial used the full original support when counting
owners. It is retained separately under `2026_10_18_ds23_family_weighting` and
is **not** mixed into this active-support benchmark. Three owned tests prevent
masked observations creating receiver votes, enforce active-point family caps,
and distinguish cross-channel from cross-receiver replication.
""".replace("TABLE","\n".join(table))
    (OUT/"README.md").write_text(body)
    write(OUT/"validation.json",dict(all_cases_present=len(per_scan)==20,
        all_variants_valid=all(r['valid'] for r in rows),
        inference_code_sha256=sha(Path(__file__).with_name('evaluate_ds23_family_weighting.py')),
        reporting_code_sha256=sha(Path(__file__)),
        source_hash_matches_protocol=sha(Path(__file__).with_name('evaluate_ds23_family_weighting.py'))==protocol['source_sha256'],
        comparison_rows=len(rows),GPS_used_only_in_report=True,paired_masks_enforced_in_fitter=True,
        original_20_scan_outputs_unchanged=True))
    print('\n'.join(table),flush=True)


if __name__=="__main__":run()
