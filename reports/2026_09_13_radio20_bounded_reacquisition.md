# Radio .20: bounded reacquisition and admission-model validation

The ARM probe can now resume acquisition at the same receive frequency after a
clean native tracking loss. The selected-window profile permits at most three
restarts, retaining a separate native journal and fresh sample epoch each time.
All 157 relevant component/operator tests pass, including synthetic loss followed
by reacquisition and 1,500 supported native measurements at both 30 and 60 MS/s.
This is implementation evidence; physical restart and sustained tracking still
require live evidence.

A separate frozen validation on existing recordings rejects deploying a universal
coarse-to-native coherence correction. The factor learned from one historical
`.20` recording agrees with 96 selected decisions from another `.20` run, but
withholds 199 native-supported measurements in the `.14` cases. No coherence or
local-correction threshold was changed.

## Bounded restart lifecycle

Firmware-worktree commit `873b7c81aee1384c5b37dd2d4e3d090b6391b98b` adds the
following lifecycle to the opt-in `--blocks 45000` profile:

1. The native controller retains each head and estimate before POP, drains its
   work and clears the epoch after acquisition loss.
2. The capture thread observes completion and joins the worker before releasing
   any IQ-owner storage.
3. A fresh snapshot must show the same native rate and epoch, drained and cleared
   state, zero faults and zero CDC/pacer drops. Only the controller's clean
   acquisition-loss result can authorize a restart.
4. The old IQ owner and native journal close. After another real refill, REBASE
   creates the next epoch. Samples before its conservative signal-center
   boundary are excluded from the new owner.
5. The ARM resumes coarse scanning and retained-IQ catch-up with the remaining
   global budget. New supported history is required before another handoff.

Source/retention errors, unread heads, cancellation and exhausted budgets stop
the run. The limits remain 200 acquisition attempts, 294.912 seconds of exported
RF, a 300-second worker deadline, 20 million retained worker samples and
2.8 million searched samples across all epochs. Each native controller permits
1,500 measurements within three seconds. At most four native episodes are
possible. The two shorter full-IQ profiles retain their existing single-episode
behavior.

The original `native.journal` is followed by at most `native-1.journal` through
`native-3.journal`. Each uses unchanged GLRJ1 framing and GLT1 payloads; a new
controller lifecycle is never appended after a previous journal's final record.
Unopened files are explicitly absent in the operator receipt. Paired coarse IQ
remains capped at the first 64 native heads across all episodes. Each pair now
records its episode; native sequence numbers restart while IQ offsets remain
cumulative.

Output distinguishes cumulative handoffs, native results, native runs, completed
native runs and reacquisitions. Completion of a bounded scan does not qualify
tracking or erase a previous native loss. The coherence gate remains 0.05 and
the existing local-correction limits and forecast horizon remain unchanged.

## Verification

The 157 passing tests run the actual pthread/FFTW worker with advancing synthetic
IQ and explicitly simulated GLT1 ports. They cover loss followed by a successful
second episode at both rates; four consecutive losses; unchanged attempt,
deadline and IQ budgets; per-epoch pairing; and refusal after source, epoch,
rate, unread-head, cancellation, deadline, retention or rebase faults.
Exclusive journal tests reject overwriting an old episode or creating a fifth.

A new independent epoch reviewer checks all source bindings, restart preflights,
individual native journals, attempt ordering, cumulative counts and paired-head
identity. Mutated evidence with a missing episode, reset budget, wrong epoch,
wrong total, misassociated pair or non-acquisition failure is rejected. This
supplements numerical acquisition review; it does not independently recompute
FPGA moments or establish physical accuracy.

The ARM binary builds with Cortex-A9/NEON optimization and warnings treated as
errors. Binary SHA-256:
`6f583eef6c79fd34033100d63e966164b9a92d2eaa39ac7b3aa5ae39466cf4f3`.

## Physical 60-MS/s check

The new executable ran on `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`, with resident image
`glrt-iq-tracking-r60000000-v1` and boot
`89459b01-4aeb-4ad1-a01b-4fe065b8ea76`. This bounded revisit used receive LO
1,690,312,496 Hz, bandwidth 2.5 MHz, manual gain 30 dB and A_BALANCED.

It stopped after 200 attempts and 227.94188 seconds of exported RF. The capture
returned 569,851,904 complex samples, with 2,796 additional exported samples at
shutdown. The new source binding used epoch 5, native counter 409,502,890,126
and conservative coarse boundary 17,062,620,422. Maximum refill interval was
12.295278 ms. Final native CDC/pacer drops and faults were zero.

Attempt 160 had six supported past measurements out of eight; every other
attempt had none. The required initial supported history was not established,
so all 200 candidates rejected and no native jobs or restarts occurred. Maximum
single-pilot ordering coherence was 0.0548085 and maximum catch-up coherence
was 0.0641058. This run exercises initial epoch binding, continuous capture,
bounded rejection and shutdown of the new executable. It does not exercise
the physical restart branch.

Independent review passes all 7,332,600 grid values, 1,600 candidate-order
scores, 3,400 resolver hypotheses, 1,600 integer-moment/dense-fit comparisons
and 3,718,521 overlapping retained samples. It verifies continuous source
counters, the new epoch binding and the six supported past observations.
The vector rotation used for replay matches 30,192 scalar-oracle cases, and
its complete arithmetic/source results agree with the scalar reviewer on the
previous 200-attempt recording. That regression uses an explicitly derived
metadata fixture; it is not another hardware run.

The operator retrieved every artifact, recorded all three unused episode
journals as absent, verified unchanged receive settings, firmware and boot,
confirmed TX-safe idle and removed its private evidence filesystem. The
executable exited zero for its completed bounded scan; tracking remains
unqualified. Paired review reports `no_pairs`, not a successful numerical
comparison. The evidence directory is `cpu-live60-reacquire-lo1690-v1/`.

## Frozen historical admission-model validation

The earlier [same-pilot analysis](2026_09_13_radio20_paired_coherence.md) measured
a median supported coarse/native coherence ratio of 2.120764966 from selected
pairs in `native-acquired-controller-20-v3`. Before inspecting the validation
pair distributions, the follow-up froze that factor and selected 96 uniformly
spaced native sequence indices from each of four other episodes.

The advisory rule requires the existing coarse support checks and coherence of
at least 0.1060382483, corresponding to the unchanged native 0.05 gate.
The comparison target is each retained native estimator's existing decision;
it is not independently labelled signal truth.

| Validation recording | Radio | Selected pairs | Both admit | Rule alone admits | Native alone admits | Both reject | Median supported coarse/native ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native-acquired-controller-20-v2, episode 0 | .20 | 96 | 95 | 0 | 0 | 1 | 2.050 |
| native-acquired-controller-v12, episode 0 | .14 | 96 | 40 | 0 | 56 | 0 | 1.445 |
| native-acquired-controller-v13, episode 0 | .14 | 96 | 0 | 0 | 67 | 29 | 1.449 |
| native-acquired-controller-v13, episode 1 | .14 | 96 | 1 | 0 | 76 | 19 | 1.443 |
| Total | | 384 | 136 | 0 | 199 | 49 | |

All 1,536 shifted coarse controls reject. The frozen shifts were ±1,000 samples
in time and ±100 kHz in frequency. These correlated coarse controls do not
establish a native detector false-alarm rate.

The review verifies complete retained-IQ and journal hashes, source
correspondence, capture closure and native ownership. It independently
recomputes all 384 native estimates from retained moments and reference-space
projection. Vector rotation agrees with the scalar integer oracle in 30,192
checks. It does not recompute those historical FPGA moments from native raw IQ.

The factor is not portable across these recordings and radios. Agreement on one
additional `.20` episode is too narrow to deploy it as a calibrated gate.
The validation used no new RF; the runtime model remains unqualified.

## Remaining work and evidence

Bounded same-frequency reacquisition is one step toward FPGA+ARM operation.
Supported live restart at both native rates, autonomous frequency revisits,
sustained feedback and longer refinement remain to be established.

Evidence is retained beneath
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.
The [evidence manifest](figures/2026_09_13_radio20_bounded_reacquisition/evidence.json)
records code, binary, frozen-plan and validation hashes and the scope of each
result.
