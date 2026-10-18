# DSX01: causal input audit and fresh regional loss surfaces

Read the [full acquisition-to-position algorithm breakdown](ALGORITHM_BREAKDOWN.md) for the GLRT, Graph tracks, causal association, calibration and position stages, and the exact construction and limitations of the 10 km loss/gradient maps.

**245 / 245 scan/configuration maps are complete.** There are six original graph association methods, 38 current correction/prior configurations and five linear-transfer configurations. These are 49 configurations, not 49 independent algorithms.

The search box is **25 × 25 km**, centered at **37.906° N, −122.545° E**. It extends ±12.5 km east/north. Maps sample a **10 km radius around that regional center**, on a 2 km grid; continuous optimizers refine endpoints. GPS is never a search start or center for these maps.

The new branch generates calibration proposals from zero, scores the entire regional Starlink candidate bank (S01 1,707; S02 1,479; S03 1,422; S04 1,427; S05 1,424), and refreshes identities at every one of the 25 regional discovery nodes. It does not read earlier fitted positions, radio states, label/alias lists or following-TLE diagnostics. Quality weights and linear nominations are regenerated from fresh same-scan evidence. A runtime read guard rejects old endpoint/seed/diagnostic inputs, and each result records actual report files opened.

**The surfaces still condition on each configuration's selected assignment branch.** Finite proposals and label refresh do not prove a global optimum over all satellite/alias combinations. A smooth conditional basin does not establish satellite identity. This qualification also applies to the convergence paths. The six original methods use 48-iteration nuisance profiles with a sparse Jacobian tested against the unchanged finite-difference objective. Initial two-step maps failed longer-refit controls and are preserved as superseded diagnostics. Saved per-pixel stop reasons expose incomplete profiling; a finite budget is not an exact global profile. Newer methods integrate nuisance coefficients (or use their declared variational approximation) at each pixel. Colors are per-method loss differences, not comparable calibrated probabilities.

The nominal/previous TLE audit requires **both collection time and element epoch ≤ the pre-scan cutoff**, checks element bytes against provenance, and binds nominal element text and bank bytes to their original hashes. The causal-history inputs cover every regional candidate. The service archive is unreadable in this session: histories therefore use available verified pre-cutoff catalogue exports, with explicitly incomplete historical depth. Earlier exports contribute orbital records only; no other scan's radio, calibration or location estimate is used. No following TLE enters the new inference.

Original graph partitions are radio-only; no points are withheld. The curved fits retain the original 12,724 curved observations. Linear methods may add nominated linear geometry but do not use linears to calibrate hardware. Candidate selection retains the existing broad 250 km visibility bank around 37.5°, −122.0° and a Starlink-name restriction. These are declared model/region assumptions, not a hand-picked satellite-ID list. The 25 km search box lies inside that broad bank region.

GLRT300 remeasurement applies to curved observations. Added linear fragments retain their original CFO and 150 Hz point-noise assumption.

Hyperparameters were developed on DSX01. Removing explicit GPS inputs does not turn this corpus into an independent new-location validation set. Published older GPS-conditioned/following-TLE diagnostics remain historical artifacts and are excluded from the new branch.

![Representative methods across five scans](overview.png)

## Position errors

Errors are km, **c0 / fitted c**. GPS evaluates already-saved fits only. No GPS winner is assembled into an algorithm. Frequency residual RMS and loss/gradient details are separate columns in [the CSV](position_and_gradient_summary.csv). No raw objective is ranked across different likelihood-power designs or different inference approximations.

| Method | S01 | S02 | S03 | S04 | S05 |
| --- | ---: | ---: | ---: | ---: | ---: |
| normal | 0.552 / 0.540 | 1.116 / 1.156 | 1.808 / 1.878 | 2.639 / 2.661 | 1.887 / 1.870 |
| clock_shared | 0.670 / 0.668 | 1.696 / 1.707 | 1.764 / 1.766 | 2.683 / 2.695 | 2.196 / 2.196 |
| clock_variance | 0.624 / 0.607 | 1.156 / 1.211 | 1.808 / 1.803 | 2.396 / 2.458 | 2.033 / 2.020 |
| tail_4 | 0.639 / 0.630 | 0.909 / 0.947 | 1.940 / 2.009 | 3.074 / 3.090 | 1.977 / 1.962 |
| tail_8 | 0.548 / 0.538 | 0.957 / 0.998 | 1.871 / 1.941 | 2.696 / 2.714 | 1.914 / 1.898 |
| balance_100 | 1.063 / 1.049 | 0.928 / 0.979 | 1.768 / 1.834 | 2.912 / 2.936 | 1.878 / 1.857 |
| balance_50 | 1.022 / 1.007 | 0.506 / 0.562 | 2.008 / 2.098 | 3.066 / 3.098 | 1.971 / 1.948 |
| quality | 0.650 / 0.631 | 0.928 / 0.967 | 1.796 / 1.866 | 2.641 / 2.663 | 1.887 / 1.870 |
| rate_0p25 | 0.554 / 0.542 | 1.116 / 1.155 | 1.809 / 1.878 | 2.675 / 2.697 | 1.890 / 1.873 |
| rate_1 | 0.586 / 0.575 | 1.104 / 1.142 | 1.807 / 1.870 | 4.190 / 4.231 | 1.939 / 1.923 |
| quality_rate_1 | 0.707 / 0.686 | 0.902 / 0.938 | 1.789 / 1.853 | 4.190 / 4.232 | 1.939 / 1.923 |
| phase_3 | 0.401 / 0.405 | 1.165 / 1.212 | 1.711 / 1.785 | 2.808 / 2.826 | 1.689 / 1.670 |
| bias_5 | 0.721 / 0.721 | 1.789 / 1.790 | 1.623 / 1.627 | 2.793 / 2.794 | 2.269 / 2.268 |
| phase_bias | 0.357 / 0.357 | 2.077 / 2.080 | 1.506 / 1.510 | 4.247 / 4.249 | 2.055 / 2.054 |
| weak_3 | 0.837 / 0.839 | 2.198 / 2.202 | 1.072 / 1.073 | 3.016 / 3.017 | 2.832 / 2.832 |
| native_rx | 0.504 / 0.492 | 0.968 / 1.012 | 1.842 / 1.916 | 2.692 / 2.717 | 2.062 / 2.049 |
| native_band | 1.714 / 1.709 | 0.658 / 0.676 | 1.962 / 2.043 | 2.703 / 2.737 | 1.553 / 1.542 |
| mixed_rx | 0.536 / 0.524 | 1.040 / 1.081 | 1.825 / 1.897 | 2.682 / 2.705 | 1.999 / 1.984 |
| rf_time_0p5 | 0.523 / 0.511 | 1.113 / 1.154 | 1.819 / 1.889 | 2.624 / 2.645 | 1.885 / 1.868 |
| rf_time_2 | 0.471 / 0.458 | 1.082 / 1.130 | 1.844 / 1.910 | 2.592 / 2.613 | 1.907 / 1.891 |
| diag_4 | 0.552 / 0.540 | 1.116 / 1.156 | 1.808 / 1.878 | 2.639 / 2.661 | 1.887 / 1.870 |
| corr_4_0p5 | 0.550 / 0.540 | 1.072 / 1.111 | 1.784 / 1.856 | 2.659 / 2.682 | 2.015 / 1.999 |
| corr_4_0p9 | 0.938 / 0.937 | 0.991 / 1.028 | 1.777 / 1.855 | 2.771 / 2.796 | 2.404 / 2.393 |
| diag_6 | 0.482 / 0.470 | 1.189 / 1.232 | 1.552 / 1.600 | 2.467 / 2.487 | 2.048 / 2.034 |
| corr_6_0p5 | 0.401 / 0.388 | 1.153 / 1.197 | 1.568 / 1.621 | 2.500 / 2.524 | 2.104 / 2.090 |
| corr_6_0p9 | 0.362 / 0.348 | 1.119 / 1.164 | 1.589 / 1.647 | 2.574 / 2.600 | 2.190 / 2.178 |
| phase_trend | 0.448 / 0.436 | 1.290 / 1.333 | 1.661 / 1.730 | 3.934 / 3.971 | 1.652 / 1.633 |
| full_trend | 1.024 / 1.013 | 1.319 / 1.364 | 1.433 / 1.498 | 2.642 / 2.662 | 2.198 / 2.181 |
| phase_history | 0.552 / 0.540 | 1.159 / 1.199 | 1.772 / 1.841 | 2.678 / 2.698 | 1.828 / 1.811 |
| full_history | 0.552 / 0.540 | 1.137 / 1.178 | 1.663 / 1.732 | 2.662 / 2.683 | 1.985 / 1.967 |
| frame_independent | 0.552 / 0.540 | 1.116 / 1.156 | 1.808 / 1.878 | 2.639 / 2.661 | 1.887 / 1.870 |
| frame_linked_700 | 0.551 / 0.540 | 1.119 / 1.158 | 1.803 / 1.867 | 2.624 / 2.643 | 1.877 / 1.857 |
| frame_linked_300 | 0.562 / 0.550 | 1.120 / 1.156 | 1.796 / 1.850 | 2.531 / 2.547 | 1.867 / 1.846 |
| frame_linked_100 | 0.561 / 0.548 | 1.119 / 1.153 | 1.837 / 1.886 | 2.176 / 2.188 | 1.989 / 1.915 |
| frame_pooled_300 | 0.546 / 0.535 | 1.123 / 1.158 | 1.896 / 1.957 | 4.132 / 4.165 | 2.564 / 2.545 |
| frame_trend_300 | 1.036 / 1.024 | 1.322 / 1.364 | 1.411 / 1.461 | 2.555 / 2.568 | 2.160 / 2.142 |
| frame_history_300 | 0.562 / 0.550 | 1.140 / 1.178 | 1.649 / 1.703 | 2.561 / 2.576 | 1.958 / 1.938 |
| frame_eccentric_300 | 0.489 / 0.476 | 1.192 / 1.231 | 1.540 / 1.573 | 2.349 / 2.358 | 2.017 / 2.004 |
| legacy_shared_phase | 1.382 / 1.390 | 0.174 / 0.202 | 1.231 / 1.292 | 4.800 / 4.819 | 3.653 / 3.715 |
| legacy_family_rate | 1.957 / 1.874 | 2.176 / 2.132 | 1.302 / 1.362 | 5.692 / 5.688 | 5.301 / 5.348 |
| legacy_orbit_em | 1.713 / 1.707 | 1.506 / 1.455 | 1.303 / 1.346 | 4.590 / 4.595 | 4.051 / 4.089 |
| legacy_penalized_split | 1.109 / 1.116 | 0.140 / 0.105 | 1.272 / 1.331 | 5.006 / 5.028 | 3.281 / 3.330 |
| legacy_correlated_noise | 2.049 / 2.025 | 1.052 / 1.031 | 1.980 / 2.070 | 4.199 / 4.349 | 3.272 / 3.304 |
| legacy_receiver_smooth | 1.815 / 1.816 | 0.649 / 0.605 | 2.160 / 2.200 | 5.354 / 5.382 | 2.156 / 2.176 |
| linear_joint | 0.541 / 0.522 | 0.939 / 0.991 | 1.951 / 1.988 | 2.571 / 2.580 | 0.907 / 0.907 |
| linear_shape | 0.498 / 0.487 | 1.049 / 1.088 | 1.895 / 1.965 | 2.679 / 2.697 | 0.863 / 0.861 |
| linear_continuation | 0.530 / 0.517 | 1.187 / 1.245 | 1.828 / 1.896 | 2.432 / 2.457 | 1.844 / 1.826 |
| linear_white_joint | 0.499 / 0.486 | 0.939 / 0.991 | 1.951 / 1.988 | 2.800 / 2.806 | 1.210 / 1.207 |
| linear_white_shape | 0.478 / 0.467 | 1.049 / 1.088 | 1.895 / 1.965 | 2.809 / 2.829 | 1.216 / 1.212 |


The [fresh-versus-previous baseline comparison](fresh_vs_previous_baseline.json) records changed labels and position errors. Earlier experiments could inherit better hypotheses from earlier blind processing of the same scan. Their performance does not establish that a new zero-initialized run will rediscover those hypotheses. This is not evidence that those earlier fits used evaluation GPS; the finite discovery/search protocols differ. Earlier results are read only by this postfit reporter and never fed to the fresh fits.

## All figures and convergence details

- [DSX01-S01 gallery](DSX01-S01/README.md)
- [DSX01-S02 gallery](DSX01-S02/README.md)
- [DSX01-S03 gallery](DSX01-S03/README.md)
- [DSX01-S04 gallery](DSX01-S04/README.md)
- [DSX01-S05 gallery](DSX01-S05/README.md)

Each two-panel figure shows c0/fitted c, downhill arrows, the regional fit endpoint, and three optimizer probes (regional center and the two lowest disk samples). Red trajectories are accepted optimizer iterates. The 10 km circle is the mapping boundary; optimization stays within the full square.

## Numerical checks and input evidence

The audit reports 245 completed scan/configuration maps, 0 pending, and 955 legacy pixels that reached the nuisance-refit iteration limit across both c arms. Those pixels are finite-budget approximations; do not interpret the legacy maps as certified global profile surfaces. Exact per-pixel stop reasons remain in each result JSON.

[Input audit](INPUT_AUDIT.md), [validation](validation.json), [GPS perturbation check](gps_invariance.json), [objective replay](endpoint_replay.json), [input hashes](input_bindings.json), [map hashes](map_bindings.json), [completed checks and limitations](VALIDATION.md), [matched tighter precision check](precision_cap_check.json).
