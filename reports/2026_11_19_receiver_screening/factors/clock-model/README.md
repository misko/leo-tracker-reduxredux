# Shared receiver oscillator in the lean position fitter

The pinned v5 marginal likelihood gives each physical receiver one smooth fractional-frequency term shared across its low and high RF groups. The lean joint fitter previously had four independent offset and linear drift pairs. The new fitter ports the v5 clock term exactly, using Gaussian centers every 30 s, a 20 s width and a 200 Hz Gaussian coefficient prior. All 11 columns per receiver are projected off the constant and linear terms on the fixed 0–300 s grid and multiplied by RF divided by 11.5 GHz. A direct comparison against the pinned basis on 429 times gave zero numerical difference. The term models carrier-frequency variation, and sample times and orbit propagation remain on the original clock.

The fit keeps the lean 2.5 s phase prior, the original joint receiver's orbit shortlist, assignment, CFO aliases, robust weights, and the three exact nonlinear range-rate relinearizations. Training and final assignment digests, including aliases and weights, matched clock-off on every real query. The new fitter uses 22 extra linear nuisance coordinates and the existing bounded least squares solver. The nonlinear objective checks each accepted step using exact shifted range rate. The original publication gates and their unmodified training anchor remain in place.

The held predictor fits position, phases and receiver terms on the existing training-only time blocks and freezes them before scoring held tracks through exact shifted range rate. Each anonymous held track selects its best existing orbit and discrete CFO alias with this frozen state. The published geographic fit uses the normal full-capture fixed-assignment refit. The exact no-clock control reproduces the as-built joint fitter's endpoints exactly across the three matched cohorts, while giving the same train-only exact held scorer as the clock model. The other measured fast controls are the as-built joint fitter, robust range-rate refinement and robust EM. The four original v5 roles come from authenticated native-request and execution archives and use the same actual captures and causal catalogue. Original role RF RMS uses its own observation support.

## Real recordings

The six timing recordings and four ID-selected confirmation recordings were sealed before geographic references were opened. The confirmation IDs DS26-0138, DS26-0154, DS26-0120 and DS26-0012 are disjoint from the earlier joint and robust-fit confirmation rosters. DS26-0012 also appeared in an earlier test of a different full-v5 solver. Three already-bound alternative tiles were confirmed outside the published site after scoring.

| Method | Timing return | Timing median error c=0 / fitted c (km) | Confirmation return | Confirmation median error c=0 / fitted c (km) |
| --- | ---: | ---: | ---: | ---: |
| Shared clock | 6/6 | 0.865 / 0.888 | 4/4 | 1.426 / 0.882 |
| Exact matched no clock | 6/6 | 1.408 / 1.150 | 4/4 | 0.960 / 1.065 |
| As-built joint | 6/6 | 1.408 / 1.150 | 4/4 | 0.960 / 1.065 |
| As-built robust exact | 5/6 | 1.667 / 1.427 | 2/4 | 0.367 / 0.309 |
| As-built robust EM | 5/6 | 1.832 / 2.136 | 3/4 | 0.972 / 0.961 |
| Original no repair | 6/6 | 0.818 / 0.832 | 4/4 | 0.961 / 0.866 |
| Original selective gap | 6/6 | 0.818 / 0.832 | 4/4 | 0.732 / 0.641 |
| Original one omitted track | 6/6 | 0.780 / 0.794 | 4/4 | 0.961 / 0.866 |
| Original omitted tracks | 6/6 | 0.780 / 0.794 | 4/4 | 0.750 / 0.682 |

The clock improved geographic error in five of six timing recordings in both arms. On the independent four it improved one of four c=0 results and two of four fitted-c results against the paired clock-off control. The paired median clock-minus-control error was −0.729 km and −0.397 km on timing, and +0.468 km and −0.217 km on confirmation. All three wrong offers were withheld by every fast method. The clock still lowered fitted RF RMS at each wrong offer.

| Cohort | Median paired clock effect on in-sample RF RMS, c=0 / fitted c (Hz) | Median paired clock effect on held RF RMS, c=0 / fitted c (Hz) |
| --- | ---: | ---: |
| Timing | −17.10 / −18.50 | −7.65 / −16.32 |
| Confirmation | −15.08 / −17.28 | +46.81 / −25.96 |
| Wrong offer, diagnostic | −66.11 / −64.35 | −49.63 / −55.19 |

Fitting the RF-dependent coefficient in the clock model lowered in-sample RMS on all ten true offers. It lowered held RMS in two of six timing and two of four confirmation recordings, and lowered geographic error in four of six and four of four, respectively. On confirmation its paired geography changes were −0.591, −0.012, −0.673 and −0.633 km for DS26-0012, DS26-0120, DS26-0138 and DS26-0154. The coefficient ablation uses the same assignments, observations and model budgets. On these data the physical clock term explains RF variation, with effects on held RF and geography that depend on the calibration arm and recording.

The clock solver's median wall time was 3.09 s for timing and 3.08 s for confirmation. Median numerical worker CPU was 2.18 s and 2.12 s. Whole worker median peak RSS was 150.5 MiB and 151.8 MiB. The matched exact no-clock had median CPU 2.12 s and 2.17 s, while the as-built joint receiver had median CPU 1.72 s and 1.85 s. These fresh measurements start at the original anonymous GLRT track projection. They include catalogue propagation and receiver inference. Historical original v5 role median wall measurements span 264–409 s across the two cohorts and include its different native-to-position execution boundary.

## New synthetic site

The same fresh synthetic native scene feeds a clean detector projection and a perturbed copy. An independent fractional-frequency disturbance applies receiver-specific phases of 95 s and 180 s sinusoids with 180 Hz and 120 Hz amplitudes after track projection, centered off the same 300 s affine grid. Both methods saw the same sealed packet for each condition. The synthetic test also supplies the perturbed projection to a wrong offer 40–55 km away.

Every synthetic fit was withheld. The two correct offers failed the normal geometry gate, and the wrong offer lacked held orbit support. On the injected scene the clock model's held RF RMS was 890 Hz and 532 Hz, compared with 936 Hz and 624 Hz for exact clock-off. Forced diagnostic errors fell from 3.20 km and 3.04 km to 2.70 km and 2.50 km. The clean and wrong-offer outcomes, including their nulls and both RF arms, remain in the synthetic receipts.

The toy regression verifies that the shared term recovers a fractional-frequency waveform across both RF groups and separates the receivers. The real confirmation reproduces an RF fit benefit and shows mixed geographic effects. The small public experiment covers one locked clock model and the original acceptance policy.

The [paired deltas figure](rf-and-position-deltas.png) plots geographic error, fitted RF RMS and held RF RMS separately for both arms, including the independently replayed ordinary-factor donors. The standard position figures use the sealed outcomes in [figures.json](figures.json). The wrong-offer chart labels every forced coordinate as diagnostic.
