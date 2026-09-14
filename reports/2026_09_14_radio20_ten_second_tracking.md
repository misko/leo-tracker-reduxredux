# Radio .20 ten-second tracking attempt

## Outcome

An opt-in 7,500-result native profile now removes the old 1,500-result limit without changing existing profiles. It runs the scheduled FPGA engine at 750 measurements/s with a ten-second result ceiling and a twelve-second controller deadline. The ARM binary built from firmware commit `ba1ae7950` passed a zero-RF load check on serial `1040005e0b100007100010000bf33a5d4d`.

The first physical run used the existing three-frame ARM catch-up cadence. It sustained exact 30 MS/s FPGA intake for 197.7745408 seconds, completed all 256 acquisition attempts at 1.2967 attempts/s, and reported no CDC or pacer drops. It did not hand off. The detailed evidence showed why: fourteen resolver attempts consumed all 200 catch-up measurements and retained as many as 96 supported history entries, but the seed was still behind the live edge. The 200 measurements at three-frame spacing cover about 0.8 seconds, while measured scan, ranking and resolution left catch-up about 1.1 seconds behind.

Firmware commit `e48891ff7` therefore added a separate nine-frame scan80 profile. It kept the same detector, acceptance gates, 200-measurement budget, 32-frame prediction horizon, evidence limits and 7,500-result native ceiling. At the measured ARM cost, nine-frame catch-up should close a 1.12-second initial backlog in about 117 measurements; the three-frame form would need more than 200. The change passed 147 component/operator tests, cross-built with warnings treated as errors, and passed another zero-RF check before collection.

The second physical run reached four handoffs in 80.0129024 seconds and completed three autonomous reacquisitions. It used 102 acquisition attempts at 1.2858 attempts/s and again reported no CDC or pacer drops. Its native episodes contained 22, 74, 17 and 23 scheduled results. Only 4 of 136 native estimates were supported, and the longest episode covered 74 results, or 98.7 ms at 750 Hz. All four ended in clean native acquisition loss. The independent 2.5-MS/s ARM observer accepted all 18 simultaneous measurements.

This is a material acquisition improvement, but it does not qualify ten-second tracking. The strict operator reports the second run as failed because the fourth clean loss occurred after the configured three-restart budget; independent epoch, ownership and journal review passes all four cleanly drained episodes. The contrast between 18/18 supported coarse observations and 4/136 supported native estimates makes native-path support the next limiter. Increasing the episode length again would not help.

| Stage | Rate | Result | Remaining risk |
|---|---:|---|---|
| FPGA IQ intake | 30 MS/s | Zero CDC/pacer drops in both runs | Longer service operation remains unqualified |
| ARM scan/rank | 2.5 MS/s source lane | 1.29 attempts/s | Candidate quality remains intermittent |
| ARM catch-up, three-frame | 250 measurements/s | Strong histories could not reach the live edge inside 200 measurements | Backlog exceeds its 0.8-second coverage |
| ARM catch-up, nine-frame | 83.33 measurements/s | Four physical handoffs and three reacquisitions | Sparse support must remain recent enough for prediction |
| FPGA scheduled tracking | 750 measurements/s | 136 results; longest episode 74 results | Native coherence support collapses almost immediately |
| ARM passive observer | 83.33 measurements/s | 18/18 supported beside the four episodes | Diagnostic only; it has no feedback authority |

The most stable next step is to use these paired episodes to isolate the native/coarse support difference and test a causal refinement or path-specific normalization on retained evidence. Any feedback change should first reproduce the existing 18 supported coarse observations, preserve the current false-positive controls, and then be admitted as another opt-in profile. The ten-second ceiling should remain in place so the next successful native-support change can be measured without another artificial two-second stop.

## Evidence and state

Machine-readable reviews are preserved for the [three-frame run](figures/2026_09_14_radio20_track10/observer3-independent-review.json), [nine-frame run](figures/2026_09_14_radio20_track10/observer9-independent-review.json), [first zero-RF check](figures/2026_09_14_radio20_track10/observer3-zero-rf-smoke.json), and [second zero-RF check](figures/2026_09_14_radio20_track10/observer9-zero-rf-smoke.json).

Both evidence sets were written to `/srv/postgres-nvme` first, copied through a RAID partial directory, checked against `SHA256SUMS`, and atomically finalized beneath `/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`. The SSD sources remain present. The radio finished on `glrt-iq-tracking-r30000000-v1`, with all IIO buffers disabled and TX powered down at -80 dB.
