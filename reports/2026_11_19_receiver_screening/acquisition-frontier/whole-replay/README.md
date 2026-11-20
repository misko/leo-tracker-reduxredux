# A differential pilot hint on two held recordings

The unconditional hint increased the number of positive probes and worsened localization on both held recordings in both calibration arms. Both candidate runs completed within 450 seconds at 512 MiB with no swap. Every candidate detector call exceeded 20 ms. [Position charts](charts/index.html) · [Measured elapsed time and detector-call distribution](resources.pdf)

The preregistered hash selection chose DS26-0168 from DS26 common127 and DS29-0604 from the eight DS29 roof16 recordings. It excluded the twelve earlier wide-roster recordings and all identified prior complete saved-IQ replays. Each capture received fresh stock and differential runs on the same two pinned cores. The original four v5 policies are separate capture-era references and give the same position within each calibration arm for these two captures. The matched stock and candidate used the same byte-verified saved IQ, original delivery clocks, supplied tile, causal TLE and phase-release solver. The adaptive proposal uses each current IQ window independently, without an orbit, location, prior target or future visit. It can replace the fourth wide center if the hinted epoch falls outside the guard around all four stock centers. [Protocol](PROTOCOL.md) · [Selection ledger](selection.json) · [Activation and scientific sources](source-lock.json)

| Recording | Arm | Stock km | Differential km | Original v5 km | Stock conditional RMS, Hz | Differential conditional RMS, Hz |
|---|---|---:|---:|---:|---:|---:|
| DS26-0168 | c = 0 | 0.805 | 1.724 | 1.515 | 70.86 | 84.76 |
| DS26-0168 | fitted c | 0.796 | 1.722 | 1.551 | 70.87 | 84.76 |
| DS29-0604 | c = 0 | 0.735 | 0.760 | 0.982 | 95.52 | 98.64 |
| DS29-0604 | fitted c | 0.734 | 0.775 | 1.041 | 95.48 | 98.59 |

| Recording | Stock → differential measured replay | Stock → differential raw stage | Stock → differential fit | Wall calls ≤ 20 ms | Positive probes gained / lost |
|---|---:|---:|---:|---:|---:|
| DS26-0168 | 219.6 → 333.9 s | 116.9 → 223.7 s | 101.7 → 109.1 s | 248 → 0 / 6,774 | 401 / 21 |
| DS29-0604 | 177.0 → 289.8 s | 110.8 → 214.8 s | 65.1 → 73.9 s | 562 → 0 / 6,756 | 401 / 17 |

The hint replaced a wide center on 8,825 of 13,548 processed DS26 receiver probes and 9,742 of 13,512 DS29 receiver probes. Each candidate preserved every original valid and invalid visit, including the 15 invalid DS29 slots. Counts and candidate-array digests are recorded for every probe. Positive means the fractional margin gate passed. The full-recording study did not verify satellite ownership of each changed probe. The two complete stock runs were measured first to make use of the time while the independent raw gate was in progress. Busy-host call latency includes the observed scheduling and cgroup effects. Resource measurements refer to the physical host cgroup and offline replay. [Per-position and RF scores](scores.csv) · [Deadline and CPU table](deadlines.csv) · [Probe comparison](probe-audit.json) · [Per-visit trace](visits.jsonl.gz)

The first DS26 candidate preflight rejected the command before systemd launched the service because the supervisor allowed only the stock module name. A scoped adapter update bound the same supervisor to the candidate module. The four physical attempts ran once each with the same limits and method settings. The untouched original rejection and proposed plan are packaged alongside the measured services. [Preflight rejection](preflight-rejection.json) · [Original attempt plan](preflight-attempt-plan.json) · [Prediction seal](prediction-lock.json)

Regenerate the scores, deadline CSV and resource figures offline with `python -m tools.pipeline_eval.qualification.frontier_whole_replay_results score <local-output>`. The standard position book uses the frozen references and predictions with `python -m tools.pipeline_eval figures --panel screening --variant frontier-whole-iq-all --out <local-output>`.
