# The signed v3 likelihood leaves 100 m omissions unresolved

The satellite-jackknife gate preserved both valid near-edge fixes and certified both containing controls with about 5.8 km of true clearance. It also kept both false fixes for receivers 100 m outside the offer. Each arm classified all four near-edge offers as unresolved. The archived v3 decision withheld the northern 52.5 km omission. The added readout took **0.127–0.231 CPU seconds** per paired fit on the two public waveforms. The gate failed the prespecified criterion for advancement. [Protocol](geographic-jackknife-protocol.md) · [Scored receipt](measurements/geographic-jackknife.json)

## Which offers are comparable

| Earlier record | Matched inputs and offered faces | Observed decision |
|---|---|---|
| Exact curved-design public sites, v3 specification `6cdbac1e…` | Both waveforms, same saved detector document and causal archive within site, 25 km offers shifted 200 m across a west or east face | Both valid fixes and both false 100 m fixes. Both 52.5 km omissions withheld. [Signed study](../single-core-2x/exact-curved-public-sites.md) |
| Installed v3 regional envelope | `north-containing` and `south-containing` are the above +100 m offers. `north-omitted` moves the northern square 52.5 km beyond truth. | Both valid fixes and one correct distant withholding. [Installed v3 receipt](../single-core-2x/measurements/regional-doppler-envelope.json) |
| Frame-plane terminal guard, `977e7dd6…` | Same northern waveform and east–west offers as v3. The signed detector document has a different digest. The 100 m omission and 52.5 km omission are separate runs. | Both northern near offers kept. The distant omission withheld. [Terminal study](../single-core-2x/terminal-guard-publication.md) |
| Released v2 and covariance `375895c3…` latitude controls | Same two public waveforms. A north or south face moves 200 m, and the offer center has a 3.125 km east–west offset. These use separate detector pins and different faces. | Both valid near-edge fixes and both false 100 m fixes in both builds and arms. [Latitude-face study](../single-core-2x/covariance-latitude-faces.md) |
| Original regional release | Same two public waveforms. The original `omitted` label refers to the 1.5 km omissions and `far` to the 52.5 km omissions. | v2 published all six offers under the original acceptance rule. [Published scores](../regional-release/blind-scores.csv) |

The exact-curved signed omission receipts use the same detector and causal archive digests as the installed v3 nearby containing controls. Both near-edge replays at each site matched their earlier signed arms, owner maps, grid, path and objective replay by exact comparison. The new report uses the published v3 owner counts throughout, 302 observations over eight satellites at the north site and 266 over seven at the south site. The maps are identical between arms and across all three fitted offers within each waveform. A cross-build check of the ordered raw-authority and carrier tuples found matching probe order, RF, probe/candidate identity, gate disposition, sample coordinates and signed CFO in v3 and covariance at both sites, and in the frame-plane northern candidate. The whole detector documents remain independently pinned. The fits see the supplied search square and screen, while the underlying waveform, receiver and causal archive are repeated within each site. [Northern signed omission](../single-core-2x/measurements/exact-curved-lookahead-north-offers.json) · [Southern signed omission](../single-core-2x/measurements/exact-curved-lookahead-south-offers.json)

## What the fixed rule measured

The rule estimates the unrestricted local mode of the signed likelihood by one Newton step and checks the predicted loss against an exact objective evaluation. It derives a second uncertainty scale by deleting one NORAD at a time, including its tracks across both receivers and its predictive entries. The retained observations keep their original owners, aliases and phase expansion. The larger curvature or jackknife scale sets the face interval, with one common simultaneous t rule. A new veto requires a common exterior face in both arms. All twelve local tests reproduced the no-deletion objective stencil exactly. Each one-step check passed. [Implementation](../../../tools/pipeline_eval/variants/experimental/geographic_jackknife.py)

Positive clearance means inside the offered face. The clearance below belongs to the unrestricted local estimate. The interval uses both sources of uncertainty. Each cell gives fixed-zero / fitted calibration.

| Longitude-face offer | Estimated clearance | Upper clearance limit | Face-normal likelihood scale | Satellite-jackknife scale |
|---|---:|---:|---:|---:|
| North, +100 m | −658 / −609 m | +2,485 / +2,573 m | 942 / 954 m | 517 / 415 m |
| North, −100 m | −876 / −838 m | +2,304 / +2,408 m | 954 / 973 m | 550 / 461 m |
| South, +100 m | +447 / +385 m | +3,209 / +3,109 m | 784 / 774 m | 417 / 372 m |
| South, −100 m | +247 / +185 m | +3,009 / +2,909 m | 784 / 774 m | 417 / 372 m |

The curvature scale governed all eight face intervals. All lower limits also fell below zero, so each interval crossed its offered face. A less conservative common threshold on standardized outward clearance would still fail. The valid northern offer is **0.70 / 0.64** likelihood standard deviations outside, and the omitted southern offer is **0.31 / 0.24** standard deviations inside. A threshold that withholds the southern omission would also withhold the northern valid fix. Requiring affirmative containment would lose both valid boundary fixes. [Point estimates, per-satellite influence and intervals](measurements/geographic-jackknife.json)

The offered-face displacement is **0.206–0.259** likelihood standard deviations in the matched near-edge tests. In a conditional Gaussian comparison with known mean alternatives 200 m apart, unbiased errors and those likelihood scales, equal-prior error is **44.9–45.9%**. At a 5% false-withhold rate, the maximum power to detect the other side is **7.5–8.3%** in that comparison. The measurements come from two repeated waveforms. The conditional scale leaves common orbit and waveform errors outside the calculation. In earlier fixed-assignment diagnostics, causal orbit error alone reversed one synthetic face comparison at each site, disjoint held timing increments did not resolve both faces, and a full southern solve using the exact later generator orbits still kept the 100 m omission. [Causal orbit diagnostic](../single-core-2x/mirrored-ephemeris.md) · [Held arrival comparison](../single-core-2x/mirrored-arrival.md) · [Southern orbit oracle solve](../single-core-2x/oracle-orbit-solve.md)

## Matched calibration outcomes

The horizontal errors and RF RMS below describe the original signed positions, which the tested gate retained. The calibration arms use the same data, selected owners and search budgets within each offer.

| Offer | Signed horizontal error, fixed zero / fitted | Solver RF RMS, fixed zero / fitted |
|---|---:|---:|
| North, +100 m | 106 / 141 m | 5.40643 / 5.16663 Hz |
| North, −100 m | 123 / 118 m | 5.41806 / 5.16725 Hz |
| South, +100 m | 817 / 1,101 m | 6.50230 / 6.39194 Hz |
| South, −100 m | 817 / 1,102 m | 6.50234 / 6.39200 Hz |
| North, wider-clearance control | 745 / 711 m | 5.37970 / 5.17265 Hz |
| South, wider-clearance control | 826 / 1,109 m | 6.50308 / 6.39235 Hz |

Fitted calibration lowered frequency RMS on every fitted offer. Horizontal error increased on the northern valid near-edge offer and on both southern near-edge offers. The gate decisions were identical in both arms. This experiment used only previously released public simulated detections and their causal orbit archive. The rule ran as an isolated diagnostic on the installed v3 solver.

## Reproduction

Run from the research worktree using the pinned ALGO08v3 installation and saved exact-curved pair directories named in the prior receipts. Inference opens no raw samples or references. The scoring step checks each pinned offer, native document, archive and build, then verifies the near-edge signed outputs and joins the released public references.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
frozen=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
out=$(mktemp -d /var/tmp/leo-geographic-jackknife.XXXXXXXX)
script=reports/ALGO08/v3/geographic_jackknife_trial.py
export PYTHONPATH="$frozen:$release/src:$release:$PWD"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
for trial in north:centered north:inside north:outside south:outside south:inside south:centered; do
  site=${trial%:*}
  offer=${trial#*:}
  flock "$lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    "$release/venv/bin/python" -BPs "$script" replay "$site" "$offer" "$out/$site-$offer.json"
done
"$release/venv/bin/python" -BPs "$script" score "$out" "$out/scored.json"
```
