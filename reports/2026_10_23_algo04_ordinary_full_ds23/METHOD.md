# Ordinary graph fit with unchanged native recovery

This is a development-informed full-DS23 regression evaluation of the ordinary-fit intervention from the five-case controlled study. It is not a blinded trial or validation at a new receiver location. The published reference remains the comparator; the previous full candidate is a rejected comparator, not a promoted algorithm. This document defines the procedure and makes no claim about its eventual results.

## Population and frozen inputs

The original manifest contains 413 recordings. The prior full candidate has 410 available recording results; DS23-0012, DS23-0184 and DS23-0286 are unavailable and remain in the full-manifest denominator. The new planned population is the same 410 recordings. Report both that denominator and 413, with fast and adaptive subsets identified by the original recording format.

Two inherited exceptions are explicit: DS23-0068 has an unqualified reference; DS23-0004 has an incomplete frozen support-aware hypothesis bank. Both retain the reference position and status rather than being counted as completed ordinary searches. The scientific search cohort therefore contains at most 408 recordings. The common completed comparison additionally requires complete prior-candidate execution and positions for all three methods in both c arms. Execution failures in the new run retain the reference as an explicitly labelled operational fallback. Such a deployed position is separate from a successful new scientific fit.

The source candidate is `/srv/bulk/leo/research/algo04-candidate-20261023`; the controlled study is `/srv/bulk/leo/research/algo04-controlled-tests-20261023`. Each usable recording reuses the stored default single-curve and support-aware hypothesis banks, including their satellite hypotheses, alias choices, masks, graph membership and priors. The procedure reruns fitting on those hypotheses. It does not rerun RF acquisition, catalogue nomination or hypothesis generation. DS23-0004 is not searched using its partial bank. The frozen inventory has 2162 trials across 409 recordings before exclusion of the seven default trials from that incomplete-bank recording.

`protocol.json` records the case list, input hashes, source hashes, budgets, exceptions and promotion criteria. `dependency_seal.json` adds loaded dependency hashes and Python/NumPy/SciPy versions, including the historical audit adapters. These files and archived sources are required for reproduction; the repository environment and the frozen prior raw banks remain prerequisites.

## Scientific intervention

Only the graph-stage fitting rule changes from the rejected candidate. Each graph trial uses five phase-update iterations with a 48-iteration ordinary position fit at each update, starting at regional coordinates (0, 0). If the initial pair fails the usual qualification gates but its minimum gate slack is at least −0.25, both c arms receive five further phase updates with up to 40 SLSQP iterations per update. This second fit optimizes the same scalar negative-twice-ELBO objective with regional bounds and ordinary numerical tolerances; it adds no residual-statistic constraints to the objective or optimizer. Eligibility still requires the unchanged gates and final phase convergence at or below 0.01 seconds.

The c = 0 and fitted-c arms use matched observations, hypothesis banks, aliases, other priors, bounds and search budgets. The near-feasible extension trigger is joint across the pair. Candidate eligibility requires both arms to qualify and to preserve the reference's accepted original observation IDs. Ranking retains the existing maximum-added-curved-points rule, deterministic component tie-break and c = 0 corrected selection loss. A trial that improves a frequency score but fails qualification is not adopted. The reference is retained when no eligible graph trial exists.

The regional center is latitude 37.906°, longitude −122.545°, with a 25 km by 25 km search region. This is the existing regional prior, not the evaluation GPS coordinate. Linear-only tracks are predictive association evidence: they do not learn the shared RF calibration coefficients, but their conditional predictive likelihood can constrain position. The fitted-c arm retains the existing curved-track calibration model.

After graph selection, native recovery runs with the existing persistent-five-second path procedure and its existing near-feasible gate-constrained native recovery. Native recovery's algorithm, priors, gates and selection policy are unchanged; its input parent can differ because the ordinary graph stage selected a different eligible trial. Thus “ordinary only” describes the graph-stage intervention, not removal of the existing native recovery procedure.

## ID protection and numerical checks

At each accepted stage, original accepted observation IDs must be preserved as a subset. Coverage is the number of unique accepted original IDs divided by all original GLRT IDs. The driver checks uniqueness, count agreement, physical-ID membership, unchanged denominator and percentage replay. Recomputed final conditional coverage must reproduce the stored accepted-ID set when graph or native recovery changes the parent.

The ordinary trial audit replays the scalar objective at the returned position and phase reference, and checks that retained curved-point counts match the graph mask. Reference, selected graph parent and final fits additionally pass the independent historical audit adapter, including legacy reference handling where required. These are numerical and conditional association checks, not independent evidence of localization accuracy. Three predefined canaries, DS23-0256, DS23-0041 and DS23-0404, compare the final positions, objectives and original-ID lists against the controlled-study no-rescue results.

Per-stage operational caps are setup 180 s, graph 1200 s, native 300 s, native near-feasible 360 s and audit 180 s. The near-feasible helper arms its own internal 360-second timer; the other timers are armed by the full driver. These caps bound individual work and may produce an explicit execution fallback; they are not scientific acceptance gates. The full driver uses 16 worker processes with one numerical thread per process. This is a desktop throughput configuration, not an embedded-runtime benchmark.

## Evaluation and decision rule

Inference uses no evaluation GPS, future TLE or new RF collection. Evaluation GPS is 37.849061591561885°, −122.48574968092912°, confined to reporting through `source/report_full.py` and its stage-diagnostic caller. The spherical position-error calculation exactly matches the published helper, as checked by a canary test. Report position-error mean, median, 90th and 95th percentiles and worst error separately from frequency RMS, score effects and association coverage. Do not infer better localization from a better in-sample frequency fit.

The reporter compares reference, rejected candidate and ordinary graph variant, retains full denominators, and supplies a common completed cohort. It lists per-recording paired changes and regressions above 0.5 km and 1 km, and paired fitted-c minus c = 0 frequency-RMS and position-error changes. Chronological circular moving-block resampling uses fixed-seed 2000 draws with 10- and 20-recording blocks; its intervals assess sensitivity to dependence within this corpus and do not establish new-location generalization. Plots show full and 0–5 km CDFs, paired errors, largest changes, association versus error and fast/adaptive distribution summaries.

The frozen promotion requirements are terminal cases with valid numerical audits; improved mean and median error in both c arms; no increase in either 95th-percentile or worst error; and no individual regression above 0.5 km in either arm. Computational eligibility additionally makes unexpected exceptions or new execution fallbacks explicit failures; the two declared inherited carries remain visible and separately audited. Scientific search completion is reported separately from terminal positions. Independent output QA must be supplied before the reporter can declare eligibility. Paired uncertainty and association are reported independently. These criteria match the prior frozen full-DS23 protocol; the report does not automatically promote a release.

## Reproduction commands

Run from `/home/mouse9911/gits/leo-tracker-reduxredux`. These commands assume the frozen bank paths and sealed historical audit dependencies already exist. The driver validates its frozen protocol and input hashes. Do not regenerate banks to make a changed input pass.

```bash
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export PYTHONPATH=/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source:/srv/bulk/leo/research/algo04-candidate-20261023/source/tools:/tmp/algo03-feasible-deps:src:tools
.venv/bin/python -B -m pytest -q -p no:cacheprovider /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/test_*.py
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/seal_dependencies.py --check
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/run_full.py --cases DS23-0256 DS23-0041 DS23-0404 --workers 3
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/run_full.py --workers 16
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/seal_dependencies.py --check
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/audit_outputs.py
.venv/bin/python -B /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/source/report_full.py --audit /srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/evidence/output_audit.json
```

Existing terminal raw results are reused by the runner; preserve logs, protocol and dependency seal when reproducing. Published copies of the protocol and dependency seal are under `evidence/`; the working evaluation expects them at its output root. The sealed absolute paths and original upstream banks must be restored for exact reproduction. The reporter reads frozen results and does not launch inference. Its tables, figures and reporting receipt include result hashes. Publication and release decisions are separate from running these commands.
