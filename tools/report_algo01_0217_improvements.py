"""Evaluation-only figures/report for the bounded scan-217 experiments."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from probe_algo01_0217_improvements import OUT, SOURCE, CASE
from report_algo01_ds23_sample import REFERENCE, position_error
from run_algo01_ds23_sample import read, sha, write


NAMES={
    "baseline_replay":"ALGO01 baseline",
    "confidence_soft":"Candidate-gap weighting, floor 0.20",
    "confidence_strong":"Candidate-gap weighting, floor 0.05",
    "confident_only_095":"Candidate confidence ≥0.95 only",
    "replicated_family_soft":"Multiple RX/channel owners: soft weighting",
    "replicated_family_only":"Multiple RX/channel owners only",
    "cross_receiver_family_soft":"Cross-RX support weighting, before gates",
    "cross_receiver_family_soft_gated":"Cross-RX support weighting + paired gates",
    "gated_matched_mask_unweighted":"Same gated mask, equal weights",
    "radio_rx_noise":"Radio-only noise estimated per RX",
    "shared_fast":"Shared short-timescale RX error",
    "radio_rx_noise_shared_fast":"Per-RX radio noise + shared fast error",
}


def collect():
    records=[]
    for prefix in ("weight_","receiver_model_"):
        for path in sorted(OUT.glob(prefix+"*.json")):
            document=read(path)
            records.append(dict(name=document["name"],label=NAMES[document["name"]],
                                arms=document["arms"],source=path.name))
    identities=read(OUT/"identity_finalists.json")
    records.extend(dict(name=r["name"],label="Identity search: "+r["name"].replace("_"," "),arms=r["arms"],
                        source="identity_finalists.json") for r in identities["finalists"] if r["name"]!="incumbent")
    whole=read(OUT/"identity_whole_family_combinations.json")
    records.append(dict(name="whole_family_best",label="Best whole-family joint replacement",
                        arms=whole["best"]["arms"],source="identity_whole_family_combinations.json"))
    recovery=read(OUT/"recovery_result.json")
    if recovery["arms"]:
        records.append(dict(name="recovery",label="Add both recovered curved tracks",arms=recovery["arms"],source="recovery_result.json"))
    for i,r in enumerate(recovery["independent_controls"]):
        records.append(dict(name=f"recovery_{i}",label=f"Add recovered track {r['new_track'].split('-')[-1]} alone",
                            arms=r["arms"],source="recovery_result.json"))
    for record in records:
        for arm,d in record["arms"].items():
            d["evaluation_error_km"]=position_error(d["endpoint_latlon"])
    return records


def summary_figures(records):
    primary=[r for r in records if r["name"] in
             ("baseline_replay","confidence_soft","confidence_strong","confident_only_095",
              "replicated_family_soft","replicated_family_only","cross_receiver_family_soft",
              "cross_receiver_family_soft_gated","gated_matched_mask_unweighted","recovery",
              "radio_rx_noise","shared_fast","radio_rx_noise_shared_fast")]
    primary.sort(key=lambda r:list(NAMES).index(r["name"]) if r["name"] in NAMES else 99)
    fig,axes=plt.subplots(1,2,figsize=(16,8.5),constrained_layout=True)
    yy=np.arange(len(primary))
    for k,arm in enumerate(("c0","fitted_c")):
        offset=(k-.5)*.32
        axes[0].barh(yy+offset,[r["arms"][arm]["evaluation_error_km"] for r in primary],height=.3,label=arm)
        axes[1].barh(yy+offset,[r["arms"][arm]["RMS_hz"] for r in primary],height=.3,label=arm)
    axes[0].set_yticks(yy,[r["label"] for r in primary],fontsize=9)
    axes[1].set_yticks(yy,[f"{r['arms']['c0']['gates']['accepted_points']}/{r['arms']['c0']['active_points']} gate points" for r in primary],fontsize=9)
    for ax in axes:
        ax.invert_yaxis();ax.grid(axis="x",alpha=.2);ax.legend()
    axes[0].set(xlabel="Position error (km)",title="Accuracy: GPS used only for evaluation")
    axes[1].set(xlabel="Conditional residual RMS (Hz)",title="Frequency fit: supports/models can differ")
    fig.suptitle("DS23-0217 · preset confidence and receiver-model experiments",fontsize=14)
    fig.savefig(OUT/"position_and_frequency.png",dpi=150);plt.close(fig)

    prep=read(OUT/"preparation.json")
    conf=prep["confidence"]
    fig,ax=plt.subplots(figsize=(11,7.5),constrained_layout=True)
    labels=[r["component"].split("0217-")[1].split("-RF")[0]+f" · {r['norad']}" for r in conf]
    ax.barh(np.arange(len(conf)),[r["confidence"] for r in conf],color="#397eab")
    ax.axvline(.95,color="crimson",ls="--",label="Preset hard-selection threshold")
    ax.set_yticks(np.arange(len(conf)),labels,fontsize=8);ax.invert_yaxis()
    ax.set(xlabel="Minimum conditional identity weight over RF endpoint and ±2 km probes",
           xlim=(0,1.05),title="Candidate uniqueness under frozen RF calibration · not calibrated certainty")
    ax.legend(fontsize=9);fig.savefig(OUT/"association_confidence.png",dpi=160);plt.close(fig)


def residual_figures():
    document=read(OUT/"residuals.json")
    tracks=[r for r in document["tracks"] if r["arm"]=="c0"]
    families=sorted({r["norad"] for r in tracks})
    colors={j:plt.get_cmap("tab20")(i%20) for i,j in enumerate(families)}
    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,constrained_layout=True)
    for rx,ax in zip((1,2),axes,strict=True):
        local=[r for r in tracks if r["receiver"]==rx]
        values=np.concatenate([r["residual_hz"] for r in local])
        seen=set()
        for r in local:
            ax.plot(r["time_s"],r["residual_hz"],".-",ms=4,lw=.6,color=colors[r["norad"]],
                    label=str(r["norad"]) if r["norad"] not in seen else None)
            seen.add(r["norad"])
        ax.axhline(0,color="k",lw=.8);ax.grid(alpha=.2)
        ax.set(ylabel="Conditional residual (Hz)",title=f"RX{rx} · {len(values)} points · RMS {np.sqrt(np.mean(values**2)):.1f} Hz")
        ax.legend(ncol=7,fontsize=8,loc="lower left")
    axes[-1].set_xlabel("Device time (s)")
    fig.suptitle("DS23-0217 baseline c=0 · residuals colored by satellite hypothesis")
    fig.savefig(OUT/"residuals_by_receiver.png",dpi=160);plt.close(fig)

    categories=[(True,True),(True,False),(False,True),(False,False)]
    labels=["Same satellite\nsame RX","Same satellite\ndifferent RX","Different satellites\nsame RX","Different satellites\ndifferent RX"]
    groups=[[r["correlation"] for r in document["pairs"] if r["arm"]=="c0" and
             (r["same_family"],r["same_receiver"])==category] for category in categories]
    fig,ax=plt.subplots(figsize=(11,5.2),constrained_layout=True)
    ax.boxplot(groups,tick_labels=labels,showfliers=False)
    rng=np.random.default_rng(217)
    for i,values in enumerate(groups,1):
        ax.scatter(i+rng.uniform(-.12,.12,len(values)),values,s=28,alpha=.8)
        ax.text(i,.95,f"n={len(values)}\nmedian {np.median(values):+.2f}",ha="center",va="top",fontsize=9)
    ax.axhline(0,color="k",lw=.8);ax.set(ylim=(-1.05,1.05),ylabel="Matched-time residual correlation",
        title="Nearest measurements within 0.5 s, ≥6 independent time pairs per track pair\nTrack-pair groups overlap; descriptive evidence, not a causal test")
    ax.grid(axis="y",alpha=.2);fig.savefig(OUT/"residual_transfer.png",dpi=160);plt.close(fig)


def identity_figure(records):
    baseline=next(r for r in records if r["name"]=="baseline_replay")["arms"]["c0"]
    sets=[("Single fragment",read(OUT/"identity_singles.json")),
          ("Mixed fragment / whole-family",read(OUT/"identity_combinations.json")),
          ("Two/three whole families",read(OUT/"identity_whole_family_combinations.json")["results"])]
    fig,ax=plt.subplots(figsize=(11,5),constrained_layout=True)
    rng=np.random.default_rng(3)
    for i,(label,trials) in enumerate(sets):
        vals=np.array([r["score"]-baseline["score"] for r in trials])
        gates=np.array([r["passing_points"]==795 for r in trials])
        for passed,marker,color in ((True,"o","#197a9f"),(False,"x","crimson")):
            use=gates==passed
            ax.scatter(i+rng.uniform(-.18,.18,int(use.sum())),vals[use],marker=marker,c=color,
                       label=("All 795 points pass" if passed else "Some original gates fail") if i==0 else None)
        ax.text(i,1.02,f"{len(trials)} proposals",transform=ax.get_xaxis_transform(),ha="center",fontsize=9)
    ax.axhline(0,color="k",ls="--",label="Incumbent RF objective")
    ax.set_yscale("symlog",linthresh=10)
    ax.set_xticks(range(3),[s[0] for s in sets]);ax.set(ylabel="RF objective minus incumbent (same 795 observations)",
        title="Expanded causal identity search · lower is better · finite proposals, not exhaustive")
    ax.legend(fontsize=8);ax.grid(axis="y",alpha=.2)
    fig.savefig(OUT/"joint_identity_search.png",dpi=160);plt.close(fig)


def recovery_figure():
    document=read(OUT/"recovery_proposals.json")
    result=read(OUT/"recovery_result.json")
    observations=read(SOURCE/CASE/"observations.json")
    chosen={r["proposal"]:r for r in result["attempts"]}
    fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for number,(proposal,ax) in enumerate(zip(document["proposals"],axes.ravel(),strict=True)):
        rx,ch,rf=proposal["lane"]
        candidates=proposal["candidates"]
        times=np.array([c["time_s"] for c in candidates])
        values=np.array([c["cfo_hz"] for c in candidates])
        lane=[o for o in observations if o["receiver"]==rx and o["channel"]==ch]
        ax.scatter([o["time_s"] for o in lane],[o["measured_cfo_hz"]/1000 for o in lane],s=12,c=".8",label="Original winning GLRT")
        for secondary,marker,color,label in ((False,"o","#168b94","Recovered winning peaks"),
                                              (True,"x","#c78a00","Recovered secondary peaks")):
            mask=np.array([not c["winner"] for c in candidates])==secondary
            ax.scatter(times[mask],values[mask]/1000,marker=marker,c=color,s=36,label=label)
        piece=proposal["model"]["piece"]
        predicted=np.polynomial.legendre.legval((times-piece["reference_time_s"])/piece["time_scale_s"],piece["coefficients_hz"])
        curve=predicted-(np.array(proposal["model"]["values"])-values)
        curve[np.r_[False,abs(np.diff(curve))>100000]]=np.nan
        ax.plot(times,curve/1000,c="#168b94",lw=1)
        attempt=chosen[number]
        satellite=next((r["norad"] for r in attempt["attempts"] if r["candidate_index"]==attempt["chosen"]),None)
        status=f"Satellite hypothesis {satellite}: passes" if satellite else "No passing causal satellite hypothesis"
        ax.set(xlim=(times.min()-3,times.max()+3),ylim=(values.min()/1000-8,values.max()/1000+8),
            xlabel="Device time (s)",ylabel="Native CFO (kHz)",
            title=f"RX{rx} CH{ch} · {len(times)} points, {sum(not c['winner'] for c in candidates)} secondary\n{status}")
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle("Radio-only recovery on probes outside the original curved calibration set")
    fig.savefig(OUT/"recovered_curved_tracks.png",dpi=160);plt.close(fig)


def report(records):
    by_name={r["name"]:r for r in records}
    table=[]
    order=["baseline_replay","confidence_soft","confidence_strong","confident_only_095",
           "replicated_family_soft","replicated_family_only","cross_receiver_family_soft",
           "cross_receiver_family_soft_gated","gated_matched_mask_unweighted",
           "best_single","best_joint","whole_family_best","recovery","recovery_0","recovery_1",
           "radio_rx_noise","shared_fast","radio_rx_noise_shared_fast"]
    for name in order:
        if name not in by_name:
            continue
        r=by_name[name];a,b=r["arms"]["c0"],r["arms"]["fitted_c"]
        table.append(dict(method=r["label"],name=name,c0_error_km=a["evaluation_error_km"],
            fitted_c_error_km=b["evaluation_error_km"],c0_RMS_hz=a["RMS_hz"],fitted_c_RMS_hz=b["RMS_hz"],
            input_points=a["active_points"],c0_passing_points=a["gates"]["accepted_points"],
            fitted_c_passing_points=b["gates"]["accepted_points"],source=r["source"]))
    with (OUT/"comparison.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    write(OUT/"evaluation.json",dict(reference_used_only_for_evaluation=REFERENCE,results=table))
    lines=["| Method | Input points | Passing c0 / fitted c | Error c0, km | Error fitted c, km | RMS c0, Hz |",
           "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['method']} | {r['input_points']} | {r['c0_passing_points']} / {r['fitted_c_passing_points']} | {r['c0_error_km']:.3f} | {r['fitted_c_error_km']:.3f} | {r['c0_RMS_hz']:.1f} |" for r in table]
    gated=by_name["cross_receiver_family_soft_gated"]
    whole=read(OUT/"identity_whole_family_combinations.json")
    residual=read(OUT/"residuals.json")
    groups=[]
    for kind,values in (("receiver",(1,2)),("channel",(1,2,3,4))):
        for value in values:
            r=next(r for r in residual["group_controls"] if r["kind"]==kind and r["removed"]==value)
            groups.append(f"| Remove {kind} {value} | {position_error(r['arms']['c0']['endpoint_latlon']):.3f} | {position_error(r['arms']['fitted_c']['endpoint_latlon']):.3f} |")
    text="""# DS23-0217: confidence weighting, receiver residuals, joint identities and additional GLRT peaks

These are bounded, single-scan development experiments on ALGO01, following
[DBG01](../DBG01/README.md) and the [original scan-217 investigation](../2026_10_18_algo01_ds23_0217/README.md).
The original benchmark is unchanged. None of these experiments demonstrates a
sub-kilometer correction. Candidate-gap weighting alone hardly moves the
position. Family-replication weighting helps more, but requires the original
gates to remain enforced; the result is still a development observation.

## Controlled inputs and scope

All inference uses the same frozen DS23-0217 radio archive, 1,411-member causal
candidate bank, latest causal TLE means, genuine earlier causal TLE uncertainty,
original 25×25 km box centered at 37.906, −122.545, Gaussian physical nuisance
priors and five phase-reference refresh rounds with at most 48 position steps
per round. Fits begin at the regional center. RF-derived endpoints are used
only for proposal screening/limited-search warm starts; final identity finalists
receive the same cold budget as the incumbent. No following TLE or GPS-selected
identity enters inference. The externally supplied GPS is used only by this
reporter for error calculation.

Every position experiment pairs c=0 and fitted-c with identical observations,
labels, alias integers, weighting, other priors and search budget. A changed
observation mask is shared between the arms. No short linear track learns
receiver calibration or orbit corrections. The scan contains CH1–4 only, so
high-versus-low-band behavior cannot be independently tested here. RX2 has
curved calibration evidence on CH1 and CH2 only.

![Position and frequency outcomes](position_and_frequency.png)

## Results

TABLE

Passing counts include the existing residual, visibility, alias and independent
owner checks. A fit using 795 points but passing fewer is an ungated proposal,
not an accepted replacement for ALGO01. RMS values on different masks are not
direct comparisons. Generalized weighted losses are not compared to unweighted
losses as normalized probabilities; lower training RMS does not establish
better localization.

## 1. What “certain association” means in this test

![Conditional association weights](association_confidence.png)

For every original curved fragment, all 1,411 satellites are screened using
a frozen RF-selected receiver calibration and a phase-plus-constant model.
Phase widths come from the same pre-scan TLE history; the constant prior is
1,000 Hz and phase is bounded by ±15 s. Costs include the Gaussian prior and
integration determinant. The score-gap weight normalizes exp(−cost/2) over
visible candidates. For stability, the minimum incumbent weight over the RF
endpoint and four ±2 km axial perturbations is retained.

This is **conditional uniqueness under an approximate model, not calibrated
identity certainty**: calibration is conditioned on, independent per-fragment
screening omits shared physical orbit modes, and a wrong model can confidently
favor a wrong identity. Final replacement fits restore the full physical model.

RX1 CH1 T002, assigned to 59859, is the one strongly ambiguous fragment:
endpoint weight about 0.614, minimum local weight about 0.521; its close
competitor is 66500. RX2 CH2 T002 has minimum weight about 0.973. All other
fragments exceed approximately 0.998. Soft powers are 0.2+0.8w and 0.05+0.95w;
the hard cutoff is w≥0.95. They were fixed without GPS tuning. These tests
mostly reweight one fragment, explaining their small effect. Removing that
fragment worsens position.

The stronger focus tests use independent ownership: “replicated” means a family
has curved support in at least two different (RX,CH) combinations and the
fragment meets the 0.95 uniqueness threshold. Soft replicated weights are 1
versus 0.2. Cross-receiver support weights are 1 for families observed on both
RXs, 0.6 for other replicated families, and 0.2 otherwise. All powers are at
most 1; no observation is counted as multiple independent measurements.
Families 57879 and 58236 provide the cross-RX support (263 of 795 input points).
The hard replicated-only test uses 587 points and worsens the estimate.

The ungated cross-RX-weighted fit improves evaluation error but one 66562
fragment crosses the unchanged quadratic residual gate: BIC gain 10.271 versus
threshold 10 at c=0. Its second fragment then fails the two-owner requirement,
so the two fragments' 75 points cannot simply remain accepted. A paired,
monotone gate/refit removes failed components from both arms and refits without
changing the weights. The table includes this gated result and an equal-weight
control on the exact same final mask, separating weighting from deletion.
The nuisance design remains fixed under masking, as in the original influence
analysis; this is a research prototype rather than a new production default.

## 2. Does the discrepancy follow receiver or satellite?

![Residuals by receiver and satellite](residuals_by_receiver.png)

At the baseline endpoint, RX1 has 598 calibration points with RMS 176.5 Hz;
RX2 has 197 with RMS 115.5 Hz. Independently estimating radio noise from graph
polynomial residuals gives 157.6 Hz for RX1 and 112.7 Hz for RX2; neither RX
selects the extra margin-dependent variance parameter by BIC. Replacing the
global radio noise by these fixed per-RX estimates changes position only a
little. It uses no orbital residuals to estimate radio uncertainty.

![Matched-time correlations](residual_transfer.png)

Track pairs match distinct measurements within 0.5 s, requiring at least six
time pairs. There are 39 track pairs per c arm. At c=0 the median correlations
are +0.37 (same family, same RX; 8 pairs), −0.06 (same family, different RX;
5 pairs), +0.54 (different families, same RX; 13 pairs), and −0.14 (different
families, different RX; 13 pairs). Cross-RX same-family pairs involve only
57879 and 58236. These overlapping, small pair sets do not provide independent
replication for 39 hypothesis tests and are not causal identification.

The stronger coherence across different families on one RX is evidence for
a receiver/acquisition-shared contribution. It does not distinguish LNB behavior,
timing or GLRT estimation artifacts, and does not rule out orbital error.
All residuals are conditioned on the existing fitted model, which already has
shared receiver smooth terms and shared family orbit terms.

| Diagnostic deletion | Error c0, km | Error fitted c, km |
|---|---:|---:|
GROUPS

Deletion preserves original nuisance design/support and masks data in matched
c pairs. RX2-only c=0 improves, but fitted-c becomes unstable in accuracy;
neither single-RX test justifies discarding RX1. Geometry and frequency-dependent
calibration are less constrained after deleting a receiver.

The bounded receiver follow-up adds shared Gaussian columns with 4 s center
spacing, 2 s width and coefficient prior sigma equal to the original radio
sigma/√2 (about 104.5 Hz). The constant and linear components are projected out
on the full 0–300 s reference grid. Separate coefficients apply to each RX,
shared by every channel/satellite on that RX. These are zero-mean nuisance
priors, not corrections learned from GPS. They are added as physical covariance
terms, distinct from deleting data or independently fitting each curve.
They reduce RMS to about 136.7 Hz, but do not resolve the position error.
Thus some shared residual structure is real enough to fit, while removing it
does not establish that it was the source of the geographic displacement.

## 3. Broader simultaneous identity search

![Expanded identity search](joint_identity_search.png)

The full candidate bank is screened at six RF-defined anchors: the incumbent
endpoint, the regional center, and four ±2 km perturbations. The two best
alternative labels per fragment from this pool give 52 single replacements.
Every proposal retains all 795 original calibration observations and is scored
with the original physical priors, not the phase/constant screening surrogate.

The next stage tests 43 joint proposals: pairs/triples of the six RF-best
distinct-fragment changes plus coherent whole-family replacements. A further
35 proposals change two or three **entire original families simultaneously**:
each operation changes every fragment bearing that original family label.
Operations are selected by RF cost, with one operation per source family.
These are 130 scored proposals in total, with overlap possible between stages,
not 130 guaranteed distinct assignments or an exhaustive combinatorial search.

All proposed alternatives have worse full-model RF objective than the incumbent.
The best tested joint alternative swaps 59859 and 66500 for RX1 CH1 T002 and
RX2 CH2 T002. It passes all 795 points but has about +6.68 RF loss and worse
position error in both c arms. The incumbent is therefore retained by the
RF-only decision rule. Better GPS error, where present among other proposals,
is not used to select labels. Passing a residual gate still does not certify
the incumbent identities.

The finite proposal pool, screening approximation and restricted pair/triple
depth remain limitations. This test substantially expands the previous
three-mode pool, but cannot rule out another coordinated identity explanation.

## 4. Additional curved evidence from alternative peaks

![Recovered curved radio proposals and satellite gates](recovered_curved_tracks.png)

Discovery excludes every physical probe already in the original 795-point
curved calibration set. It retains all remaining gated GLRT peaks, clusters
circular-frequency replicas within 300 Hz, and proposes quadratic/cubic curves
using 1,800 deterministic seeds per RX/channel/actual-RF lane. Seeds are proposals
only: final fits use the frozen degree≤4, 150 Hz noise, ±450 Hz membership,
support, gap, complexity and structure checks. At most one peak per physical
probe is selected, and added tracks have exclusive physical ownership.
Curved eligibility still requires ≥20 s and ≥250 Hz deviation from an affine
fit. A fixed 2log(1800) discovery-search penalty is included in the proposal
gain; it is not a calibrated false-alarm guarantee.

Four exclusive radio curves pass these checks. Full-bank causal satellite
screening and exact phase-shifted follow-up accept two:

| New hypothesis | Lane | Span, s | Points | Winning / secondary | Curvature RMS, Hz |
|---|---|---|---:|---:|---:|
| 63936 | RX1 CH3 | 0.273–32.706 | 22 | 15 / 7 | 951.2 |
| 65203 | RX2 CH4 | 126.659–150.446 | 16 | 14 / 2 | 1072.8 |

Neither was selected by a satellite whitelist. The other two radio curves
(RX2 CH1 at 258–278 s, RX2 CH2 at 100–128 s) fail the tested satellite gates.
The RX1 CH1 243–270 s fragment discussed earlier is not recovered under these
unchanged tests; its secondary continuation also uses probes already assigned
to an original calibrating curve and cannot be added as independent votes.

The accepted curves add 38 physical-probe factors: 29 original winning peaks
and nine secondary selections. They are not 38 extra original winning GLRT
points. Physical probe IDs remain stable while selected peak metadata records
the alternative choice. None of these probes was originally associated in
the saved baseline. We do not claim a new full-scan association percentage:
this experiment evaluates 833 calibration factors, not a full reassignment of
every original short/linear extension.

Both new curves pass the existing joint residual/alias/visibility/support gates
after position refit, but position worsens. Each is also evaluated individually
against the original calibration set, without allowing the absent new track
to create extra two-owner requirements or orbital nuisance modes;
both individual additions worsen position. This is direct evidence that a
larger accepted count and lower residual RMS are insufficient quality metrics.
The added identities and independence assumptions remain hypotheses to audit.

## Interpretation and next use

The tested weak association is not the main driver. Independent family support
is a more useful weighting signal than the current conditional score gap on
this scan, but the gated result is still several kilometers off. The same-mask
equal-weight control is necessary to attribute any benefit to weighting.
The receiver-shared residual signal does not explain the entire displacement:
modeling it improves RF fit substantially without comparable geographic gain.

Keep these as development variants. Before changing ALGO01, freeze the
replication weights and paired-gate rule and test them on untouched scans/sites;
do not tune weights or delete families to minimize this scan's GPS error.
Further diagnosis should examine independent timing/CFO evidence and the
new 63936/65203 hypotheses across receiver/channel support, rather than
increasing every satellite's nuisance freedom or forcing the missing arc.

## Reproduction and validation

The inference tool is `tools/probe_algo01_0217_improvements.py`; the
evaluation-only reporter is `tools/report_algo01_0217_improvements.py`.
Use the repository .venv, PYTHONPATH=src:tools, OPENBLAS_NUM_THREADS=1 and
OMP_NUM_THREADS=1. Run stages in this order: `prepare`; `weighted`,
`replicated_weights`, `residuals`, `identities`, `recovery`, `receiver_models`;
then `family_combinations` and `gated_weight`; finally the reporter.
Independent numerical stages may run as bounded subprocesses. No new RF or
QNAP mutation is involved. Source snapshots/hashes and scientific controls
are recorded in [validation.json](validation.json).

Six synthetic tool tests cover confidence powers/normalization, full-bank
visibility and alias invariance, unique probe votes, receiver basis affine
projection, and recovery of a known curved signal through the native gates.
The baseline endpoint replay reproduces the original objective and position;
all changed c pairs share their data/masks and discrete hypotheses. Existing
benchmark fixtures and runtime components are unchanged.

[Numerical comparison CSV](comparison.csv) · [Evaluation JSON](evaluation.json) ·
[RF preparation and candidate pool](preparation.json) ·
[Residual pairs and group controls](residuals.json) ·
[Joint whole-family search](identity_whole_family_combinations.json) ·
[Recovered-peak evidence](recovery_proposals.json) · [Recovery fits](recovery_result.json)
"""
    text=text.replace("TABLE","\n".join(lines)).replace("GROUPS","\n".join(groups))
    text=text.replace("The nuisance design remains fixed under masking",f"The gated fit reaches {gated['arms']['c0']['evaluation_error_km']:.3f} km at c=0 and {gated['arms']['fitted_c']['evaluation_error_km']:.3f} km with fitted c, retaining {gated['arms']['c0']['active_points']} input points. The nuisance design remains fixed under masking")
    (OUT/"README.md").write_text(text)
    source=Path(__file__).resolve().parents[1]
    files=[source/"tools/probe_algo01_0217_improvements.py",Path(__file__),
           source/"tests/analysis/test_algo01_0217_improvements_tool.py"]
    prep=read(OUT/"preparation.json")
    changed=[f for f,h in prep["inputs"].items() if sha(Path(f))!=h]
    assert not changed
    baseline=by_name["baseline_replay"]
    original=read(SOURCE/CASE/"result.json")
    for arm in ("c0","fitted_c"):
        assert abs(baseline["arms"][arm]["score"]-original["arms"][arm]["record"]["score"])<1e-5
    for r in records:
        a,b=r["arms"]["c0"],r["arms"]["fitted_c"]
        assert a["active_points"]==b["active_points"]
        assert [t["component"] for t in a["gates"]["tracks"]]==[t["component"] for t in b["gates"]["tracks"]]
    write(OUT/"validation.json",dict(inputs_unchanged=True,baseline_replay_tolerance=1e-5,
        source_sha256={str(f.relative_to(source)):sha(f) for f in files},
        initial_source_snapshot_sha256=sha(OUT/"source_initial.py"),
        initial_snapshot_matches_preparation=sha(OUT/"source_initial.py")==prep["source_sha256"],
        paired_counts_and_component_lists_verified=True,tests_passed=6,
        GPS_used_only_by_reporting=True,baseline_runtime_components_unchanged=True,
        report_figures=sorted(f.name for f in OUT.glob("*.png"))))
    print("Report:",OUT/"README.md",flush=True)
    for r in table:
        print(r["name"],round(r["c0_error_km"],3),round(r["fitted_c_error_km"],3),r["c0_passing_points"],"/",r["input_points"],flush=True)


if __name__=="__main__":
    records=collect()
    summary_figures(records)
    residual_figures()
    identity_figure(records)
    recovery_figure()
    report(records)
