"""Render the comparison and assemble the scripts and measured results for review."""

import base64
import csv
from html import escape
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cold_replay as cold
from score_evidence import score_xy


ROOT = Path(__file__).resolve().parent
GIT = "https://github.com/misko/leo-tracker-reduxredux/blob/db94afc0d/"


def load(name):
    return json.loads((ROOT/name).read_bytes())


def table(headers, rows):
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>"+"".join(f"<td>{v}</td>" for v in row)+"</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def link(url, label):
    return f"<a href='{escape(url,quote=True)}'>{escape(label)}</a>"


def distribution(x):
    x = np.asarray(x)
    return tuple(float(v) for v in (np.mean(x),np.median(x),np.percentile(x,95),np.max(x)))


def positions(ev, stream, combined):
    estimates = {}
    names = dict(v5="Fast v5 baseline", stream="Online tracks + compact fit",
                 stream_consensus="Online tracks + family consensus",joint="Graph tracks + compact fit",
                 consensus="Graph tracks + family consensus", diverse12="12-track geometry selection",
                 shape="Frequency changes only",soft_grid="Satellite-mixture map")
    for method in names:
        estimates[method] = {arm:{} for arm in ("c0","fitted_c")}
    for case,methods in ev["per_case"].items():
        for method,arms in methods.items():
            for arm,row in arms.items():
                if row.get("status")=="estimate":
                    estimates[method][arm][case] = (row["error_km"],row["rms_hz"])
    for row in stream["rows"]:
        for arm,fit in row.get("arms",{}).items():
            if fit.get("status")=="estimate":
                error = score_xy(fit["xy"])
                estimates["stream"][arm][row["case"]] = (error,fit["rms_hz"])
    for row in combined:
        for arm,fit in row.get("arms",{}).items():
            if fit.get("status")=="estimate":
                estimates["stream_consensus"][arm][row["case"]] = (score_xy(fit["xy"]),fit["rms_hz"])
    return estimates,names


def plot(estimates,names,common,prefix):
    fig,(left,right) = plt.subplots(1,2,figsize=(12.0,4.8),gridspec_kw=dict(width_ratios=(1.27,1)))
    fig.subplots_adjust(left=.235,right=.978,top=.82,bottom=.17,wspace=.32)
    for i,(tag,color) in enumerate((
        ("v5","#253854"),("stream_consensus","#0b776d"),("consensus","#0b776d"),("joint","#497a95"),
        ("stream","#497a95"),("diverse12","#8992a1"),("shape","#8992a1"),("soft_grid","#8992a1"))):
        y = 7-i
        vals = [estimates[tag]["fitted_c"][case][0] for case in common]
        _,med,tail,_ = distribution(vals)
        left.plot([med,tail],[y,y],lw=2,color=color,solid_capstyle="round")
        left.plot(med,y,"o",color=color,ms=7)
        left.plot(tail,y,"|",color=color,ms=12, mew=2)
    order = ["v5","stream_consensus","consensus","joint","stream","diverse12","shape","soft_grid"]
    left.set_yticks(range(7,-1,-1),[names[s] for s in order],fontsize=9.5)
    left.set_xlim(0,9)
    left.set_xlabel("Horizontal error (km)")
    left.set_title(f"Same {len(common)} scans · fitted c",loc="left",fontweight="bold",fontsize=13,pad=27)
    left.text(.0,1.017,"Dot = median, tick = 95th percentile",transform=left.transAxes,fontsize=9,color="#4e5967")
    times = [60,120,300]
    for quantile,color,label in (("median","#0b776d","Median"),("p95","#9d5529","95th percentile")):
        y = [prefix[t+"-fitted_c"]["position_km"][quantile] for t in ("60","120","full")]
        right.plot(times,y,marker="o",color=color,label=label,linewidth=2.2,ms=6)
        for x,v in zip(times,y):
            right.annotate(f"{v:.1f}",(x,v),xytext=(0,8),textcoords="offset points",ha="center",color=color,fontsize=9)
    right.set(xlabel="Seconds of radio observed",ylabel="Horizontal error (km)",xticks=times,ylim=(0,10))
    right.set_title("How long to listen?",loc="left",fontweight="bold",fontsize=13,pad=27)
    right.text(0,1.017,"Online tracks + compact fit, 32 scans",transform=right.transAxes,fontsize=9,color="#4e5967")
    right.legend(loc="lower left",frameon=False,fontsize=9)
    for ax,axis in ((left,"x"),(right,"y")):
        ax.set_axisbelow(True)
        ax.grid(axis=axis,color="#dce1e6",lw=.7)
        ax.spines[["right","top"]].set_visible(False)
        ax.spines[["left","bottom"]].set_color("#9aa4af")
        ax.tick_params(axis="both",length=3,color="#9aa4af")
    png = ROOT/"position-tradeoffs.png"
    fig.savefig(png,dpi=165,bbox_inches="tight",pad_inches=.23,facecolor="white")
    plt.close(fig)
    return png


def main():
    ev = load("evaluation.json")
    pref = load("stream/winner-scores-32.json")
    combined = load("stream-consensus.json")
    estimates,names = positions(ev,load("stream/winner-positions-all.json"),combined)
    common = sorted(set.intersection(*(set(arms[arm]) for arms in estimates.values() for arm in arms)))
    file_rows = []
    stats = {}
    for method,arms in estimates.items():
        for arm,data in arms.items():
            for cohort,labels in (("all available estimates",sorted(data)),("common with v5",common)):
                errors = [data[c][0] for c in labels]
                rms = [data[c][1] for c in labels]
                mean,median,p95,maximum = distribution(errors)
                row = dict(method=method,arm=arm,cohort=cohort,n=len(labels),mean_km=mean,median_km=median,
                           p95_km=p95,maximum_km=maximum,median_selected_rf_rms_hz=float(np.median(rms)))
                file_rows.append(row)
                stats[method,arm,cohort] = row
    with (ROOT/"position-comparison.csv").open("w") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(file_rows[0]))
        writer.writeheader()
        writer.writerows(file_rows)
    png = plot(estimates,names,common,pref)
    encoded = base64.b64encode(png.read_bytes()).decode()
    times = load("paired-native-timing.json")
    clocks = {m:distribution([r["wall"] for r in times["rows"] if r["mode"]==m])
              for m in ("stream","batch")}
    all_fitted = {tag:stats[tag,"fitted_c","all available estimates"] for tag in names}
    combo = all_fitted["stream_consensus"]
    ranking = [
        ("1","Online track and position solver",
         "Keep at most eight moving frequency tracks per receiver and channel. Confirm with six hits. Compress the curved tracks and fit one regional position with shared receiver biases and satellite timing corrections.",
         f"158/159 outputs. Median {all_fitted['stream']['median_km']:.2f} km, P95 {all_fitted['stream']['p95_km']:.2f} km. A first track appeared at 3.2 s median. A 60 s position was much less accurate than the full scan.",
         "Port the tracker and matching kernel. Measure time to a useful fix and build an abstention rule for weak geometry."),
        ("2","Guided pilot detector with periodic blind search",
         "Follow recent peaks in frequency and frame timing. Search blindly every eighth visit or on loss of lock. Use a folded correlation search to propose a few candidates for an exact pilot check.",
         "Full DS26 saved-peak replay retained 590,338/692,210 original winners at ≤31.1% normalized search area. On 32 scans, guided input raised mean position error by 92 m (c=0) and 93 m (fitted c).",
         "Main end-to-end timing risk. Measure search, false detections and recovery from loss of lock on 10 MS/s IQ on the intended board."),
        ("3","Consensus across satellite families",
         "Draw 16 sets of six proposed satellite IDs. Fit from each set, score across entire satellite families, then refit the families agreeing on a position. Prevent repeated tracks from one satellite from dominating the vote.",
         f"On graph tracks, {all_fitted['consensus']['median_km']:.2f} km median and {all_fitted['consensus']['p95_km']:.2f} km P95. With online tracks, {combo['median_km']:.2f} km and {combo['p95_km']:.2f} km, {combo['n']} estimates.",
         f"Use a fixed work budget in the online estimator. Its worst scan missed by {combo['maximum_km']:.1f} km; several mutually consistent wrong IDs can still win."),
        ("4","Compact batch solver with a local Doppler table",
         "Keep the anonymous graph builder. Propagate the sky once, summarize each curved track with 12 measurements, keep 12 satellite candidates per track, vote in 49 map cells, then solve for continuous coordinates.",
         f"{all_fitted['joint']['median_km']:.2f} km median, {all_fitted['joint']['p95_km']:.2f} km P95. It contained v5’s majority ID in 1,423/1,423 checked shortlists. Median paired-timing run {clocks['batch'][1]:.2f} s from saved GLRT candidates.",
         "Good first numerical reference. The offline graph consumed most of the host time; the sky table requires regional coverage and fresh causal elements."),
        ("5","Stationary installation with occasional fresh fixes",
         "Run an anchor solve every fourth scan. Between anchors, average up to four already available anchor coordinates and expose the age of the prediction.",
         "36/40 scheduled v5 anchors completed. On 142 pairs the forecast had a 474 m median at c=0 and 459 m with fitted c. The median age of the latest anchor was 2.51 hours.",
         "Best if the antenna is bolted down and an aged estimate is acceptable. Relocation requires fresh RF acquisition. The 142 successive result pairs shared zero satellite IDs."),
        ("6","Select 12 tracks by geometric information",
         "Greedily choose curves whose slopes add independent east/north information after accounting for orbital timing error. Cap the final regression at 12 tracks.",
         f"All available scans returned a coordinate. Median {all_fitted['diverse12']['median_km']:.2f} km and P95 {all_fitted['diverse12']['p95_km']:.2f} km. Its candidate nomination still examined up to 64 tracks.",
         "Useful under a tight solver-memory ceiling. The current 12-track policy gives up too much tail accuracy as a general default."),
        ("7","Frequency changes only",
         "Subtract each track’s own average and solve from its changing shape. This cancels constant offsets and the RF-dependent calibration term within each track.",
         f"The c arms agree as the algebra predicts. Median {all_fitted['shape']['median_km']:.2f} km, P95 {all_fitted['shape']['p95_km']:.2f} km, 15 boundary results.",
         "A calibration-independent control or fallback. Losing the absolute level also discards information about position."),
        ("8","A probability grid with competing satellite IDs",
         "Score a 9×9 map. Each track contributes a mixture over 12 candidate satellites plus clutter; integrate its timing uncertainty and fit shared calibration per cell. Return the best cell.",
         f"Median {all_fitted['soft_grid']['median_km']:.2f} km, P95 {all_fitted['soft_grid']['p95_km']:.2f} km. A 3.125 km cell spacing and independent track timing errors limit this version.",
         "Useful when an explicit map of competing hypotheses matters. The map weights require calibration before use as confidence probabilities."),
        ("9","One timestamp per pass",
         "Reduce a curved track to the time at which its frequency drops fastest. Intersect the predicted event times of several satellites to locate the antenna.",
         "Even with identities supplied by v5, 142 fits gave 7.01 km median, 19.14 km P95 and 57 boundary solutions. Moving the receiver 1 km changed event time by only 0.147 s along the most sensitive direction.",
         "Drop as a standalone fix. Event time can still help propose an identity if other measurements verify it."),
        ("10","Tiny network predicting coordinates directly",
         "Train a small model on frequency-track summaries and orbit context; inference would have a fixed cost.",
         "A no-radio control that memorized the first DS26 coordinate scored 0 m on the other 158 labels and 0.75 m on all 615 DS29 references. A network was unnecessary for this test.",
         "Defer coordinate regression until geographically separated sites are held out. Learning to rank satellite candidates would need its own identity/coverage experiment."),
    ]
    ranktable = table(["Rank","Design","How it works","Sanity check","Engineering decision"],ranking)
    numeric_rows=[]
    for tag in names:
        a,b = (stats[tag,arm,"common with v5"] for arm in ("c0","fitted_c"))
        numeric_rows.append([names[tag],str(a["n"]),f"{a['median_km']:.2f} / {b['median_km']:.2f}",
                             f"{a['mean_km']:.2f} / {b['mean_km']:.2f}",f"{a['p95_km']:.2f} / {b['p95_km']:.2f}",
                             f"{a['median_selected_rf_rms_hz']:.0f} / {b['median_selected_rf_rms_hz']:.0f}"])
    numerics = table(["Estimator","Cases","Median km","Mean km","P95 km","Selected RMS, Hz"],numeric_rows)
    report = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ten designs for embedded Doppler positioning</title><style>
*{{box-sizing:border-box}}body{{max-width:1180px;margin:3rem auto;padding:0 2rem;color:#182a38;font:16px/1.55 Inter,system-ui,sans-serif}}
h1,h2{{line-height:1.16;color:#142d44}}h1{{font-size:clamp(2rem,4.2vw,3.4rem);max-width:930px}}h2{{margin-top:2.2rem}}p{{max-width:96ch}}a{{color:#086255}}img{{width:100%;height:auto}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:.88rem}}th,td{{padding:.65rem .55rem;text-align:left;vertical-align:top;border-bottom:1px solid #ccd7de}}
th{{background:#eaf1f4;color:#263f51}}td:first-child{{font-weight:600}}code{{font-size:.87em}}@media print{{body{{margin:0;padding:0;font-size:10pt}}tr,img{{break-inside:avoid}}h2{{break-after:avoid}}}}
</style><main><h1>Ten designs for embedded Doppler positioning</h1>
<p><strong>Build the streaming receiver, try a fixed satellite-consensus budget, and move the next hardware measurement to the pilot detector.</strong>
The simple streaming estimator ran in {clocks['stream'][1]:.2f} s median on one x86 core starting with saved pilot candidates. Adding the consensus step gave {combo['median_km']:.2f} km median error across {combo['n']} scans and took {np.median([r['both_arms_wall_s'] for r in combined if 'both_arms_wall_s' in r]):.2f} s median for that complete post-detector path in a separate single pass per scan. It used up to five minutes of observed radio. The DS26 accuracy cost and the detector’s ability to keep up with incoming samples drive the decision.</p>
<h2>Ranked proposals</h2><p>The ranking favors a fresh position from a single receiver with a coarse regional prior. The stationary forecast answers a different product need. The detector and consensus options can be combined with the position solver. Geographic figures in this table use fitted c unless both arms are given. Values for full-corpus new solvers include all available inputs.</p>{ranktable}
<h2>Matched position comparison</h2><p>The following rows use exactly the same {len(common)} DS26 recordings. Each cell shows <strong>c=0 / fitted c</strong>. Both arms receive the same input tracks, candidate lists, priors on other parameters, and search budgets within each method. The fixed-c control removes the receiver frequency correction proportional to tuned GHz minus 11.5. Subtracting each track mean eliminates this term identically.</p>{numerics}
<p>RMS is the median across scans of the fitted frequency residual in hertz on each method’s own selected samples. Changes in selected observations and offsets affect that measure. The shape-only value uses demeaned residuals. The position columns use the independent evaluation coordinate. For example, across 158 streaming estimates the fitted coefficient lowered median RMS from 197 to 180 Hz while median position error moved from 2.150 to 2.156 km.</p>
<figure style="margin:2rem 0"><img alt="Matched position error and how position error changes with observing time" src="data:image/png;base64,{encoded}"></figure>
<h2>Starting points and timing</h2>
<p>DS26 contained 159 fast scans. DS26-0172 lacked a native input. The five anonymous-graph models and the ordinary streaming solver produced 158 coordinates each; v5 repeat zero completed 143 runs. The published performance report uses a stricter common cohort of 127 successes across four configurations and two repeats. A returned coordinate records numerical availability. The simple solvers still need a calibrated way to withhold weak fixes.</p>
<p>For the closest hardware-neutral comparison, I timed two code paths from the same saved GLRT candidate file through both calibration fits, including parsing, track construction, a fresh causal catalogue read and orbit propagation. Four predetermined recordings were each run five times with alternating order on one pinned Intel Core Ultra 9 285K core, one BLAS thread, and a busy host. The streaming version took {clocks['stream'][1]:.3f} s median (range {min(r['wall'] for r in times['rows'] if r['mode']=='stream'):.3f}–{clocks['stream'][3]:.3f}). The graph version took {clocks['batch'][1]:.3f} s (range {min(r['wall'] for r in times['rows'] if r['mode']=='batch'):.3f}–{clocks['batch'][3]:.3f}). Each timed output reproduced its earlier coordinates in both arms. The process high-water mark across alternating paths was {max(r['max_rss_kib'] for r in times['rows'])/1024:.0f} MiB. A packed float32 orbit table for a typical scan would occupy 1.12 MiB, plus buffers, tracks, catalogue and solver storage. Actual inference used floating-point host arrays.</p>
<p>The original v5 mean of 445 s includes additional scientific stages and figures. Across the 254 matched baseline workers, initial fitting, conservative refitting and family comparison averaged 228 s in total. Figure evidence and rendering averaged 36 s. Deleting figures alone would leave most of the computation. Both v5 and these backend clocks start downstream of raw pilot detection.</p>
<p>DS26 fast scans visited a pair of receivers every 44.30 ms at the median. In a separate physical PLUTO+ RAM-replay test, a sparse detector at 10 MS/s averaged 302.71 ms per dual-receiver dwell with a maximum of 424.70 ms on eight dwells repeated twice. Its 120 ms dwell schedule differs from DS26. The directed-search tests here restrict the available candidates in an archive. Only an on-board test can convert the allowed search area into a processing rate.</p>
<h2>What the experiments could distinguish</h2>
<p><strong>Association.</strong> The cold solvers use anonymous curved tracks, the configured 25 km square and the newest available snapshot preceding the start, with only Starlink elements whose epoch is also within the preceding 48 hours. They fit shared receiver/band offsets and drift, an optional RF slope and a timing correction per satellite. Selection in the main compact fit is capped at 64 tracks, 12 samples and 12 possible IDs per track, followed by four reweighted linear solves. Satellite-family consensus adds 16 six-family proposals. The comparison with v5 owner labels runs afterward. Of 1,423 curved tracks with ≥80% ownership by one v5 satellite on the 32-scan panel, its ID appeared in all 1,423 shortlists. Of the 1,359 such tracks accepted by the compact solver, 1,321 selected that ID. Agreement with v5 is evidence about pruning, not independent satellite identity verification.</p>
<p><strong>Causal operation.</strong> All 158 native files and graph files matched their frozen hashes. On DS26-0002, deleting every future observation reproduced exactly the tracks from the 60 s prefix. Across 158 scans the online algorithm tested 1.24 continuations per arriving winner and produced its first confirmed fragment at 3.20 s median. Final chronological linking agreed with 90.0% of offline graph points at 86.0% precision under one-to-one matching. Completed fragments are retained in the Python prototype. The eight-state cap applies to active tracks per lane.</p>
<p><strong>Pilot acquisition.</strong> A detector search using up to three recent peaks per lane and ±8 kHz / ±25 µs windows retained 85.28% of original winners across 2,133,140 probes. Reacquiring every fourth visit raised recovery to 90.29% while expanding the candidate search area to ≤40.61%. On a separate 2.5 MS/s DS9 raw-IQ development set, a two-lag folded correlator with five frequency aliases put the reference timing and frequency in its top four for 103/105 positives. Verification still matters. A held-session score threshold correctly accepted 62/105 positives and accepted 3/55 reference-empty probes. The five-alias choice used this development panel. Direct access to DS26 10 MS/s raw IQ was unavailable; its front-end numbers use saved candidates.</p>
<p><strong>Reference leakage and geography.</strong> Error evaluation uses the operator-confirmed site and the same distance formula as the frozen report. No GPS location, previous position or v5 identity enters cold inference. The event-only diagnostic supplies archived identities on purpose. The stationarity experiment reads prior v5 coordinates only after the anchor could have finished and supplies no current RF. As a plumbing check, a synthetic fixture generated exact SGP4 measurements with clock offsets, drift, per-satellite timing errors, noise and injected outliers for four displaced sites in each of four epochs. Both c arms recovered the correct quadrant on all 16 cases. These simulated sites exercise sign and position sensitivity; field evidence still comes from the single DS26 roof.</p>
<h2>Decision on the device</h2>
<p>Replay stored 10 MS/s IQ at the measured arrival cadence on the intended board. Compare full blind acquisition and guided acquisition with a blind fallback through the same streaming backend. Log maximum queue depth, dropped visits, peak RAM, time to a useful fresh fix, position tails and abstentions. A board that needs a sub-kilometer median has a harder accuracy requirement than the fresh single-scan prototypes demonstrated. A permanently fixed antenna can instead offer an explicitly aged position between anchor solves.</p>
<p>{link(GIT+'docs/analysis/algo07v5-ds26-performance.md','Pinned v5 benchmark')} · {link(GIT+'reports/2026_09_30_arm_standard_comparison/README.md#L180-L187','PLUTO+ timing measurements')} · {link(GIT+'reports/2026_09_29_arm_two_lag_proposals/REPORT.md','Earlier two-lag proposal study')} · {link(GIT+'reports/2026_10_19_ds23_stationary_consensus/README.md','Earlier stationary-receiver study')} · {link('https://doi.org/10.1109/vtc2023-spring57618.2023.10199264','Primary research on blind Starlink Doppler tracking')}</p>
<h2>Reproducing the checks</h2>
<p>The bundle includes the per-case outputs, scripts and calibration-arm summaries. Reprocessing requires the frozen DS26/DS9 radio archives referenced by the scripts on the analysis host. The publication data in the bundle can be inspected independently. The original replay used the repository virtual environment with NumPy, SciPy and SGP4, one BLAS thread, and the pinned source tree below.</p>
<pre style="white-space:pre-wrap">export PYTHONPATH=/home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/src
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
py=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
"$py" cold_replay.py --output cold-panel.json
"$py" cold_replay.py --remaining --output cold-remainder.json
"$py" alternative_replay.py --output alternative-panel.json
"$py" alternative_replay.py --remaining --output alternative-remainder.json
"$py" stream/winner_to_fix.py --count 32
"$py" stream/winner_to_fix.py --all-full
"$py" stream_consensus.py</pre>
<p>The data shape in the online solver is one observation time, channel, receiver, RF and CFO per accepted probe. Each active track carries a timestamp, frequency and slope. References to the graph and v5 controls in the scoring scripts support agreement and position-error calculations after inference. The historical timing scopes and the prototype measurement scopes differ. Production code and radio settings were unchanged.</p>
</main></html>"""
    (ROOT/"embedded-position-study.html").write_text(report)
    members = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in
               (".json",".csv",".html",".png",".py") and "__pycache__" not in p.parts]
    with ZipFile(ROOT/"embedded-position-evidence.zip","w",compression=ZIP_DEFLATED) as z:
        for path in sorted(members):
            z.write(path,path.relative_to(ROOT))


if __name__=="__main__":
    main()
