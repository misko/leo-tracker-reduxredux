# First-use replay maps from the signed original recordings

The normal no-prior-map producer completed both physical recordings. It
matched the ordinary 20/8 science and published 14 durable maps that
matched the independently prepared copies byte for byte. Against the
archived installed v3 clocks, median wall speedup was **1.750×** and
summed wall speedup was **1.390×**. The median clears 1.6× and the sum
falls short. Both 2× gates fail.

| Physical recording | Installed v3 wall / CPU | Ordinary 20/8 wall / CPU | Normal first-use wall / CPU | Outcome |
| --- | ---: | ---: | ---: | --- |
| DS30-0107 | 1.497018 / 1.495600 s | 0.548607 / 0.547318 s | **0.562754 / 0.561340 s** | Curvature withhold |
| DS30-0016 | 10.744677 / 10.742462 s | 8.629779 / 8.611184 s | **8.243089 / 8.217620 s** | Both arms complete |
| Sum | 12.241696 / 12.238062 s | 9.178386 / 9.158502 s | **8.805843 / 8.778960 s** | |

Median speedup is the reciprocal of the median candidate-to-control time
ratio across the two recordings. Against installed v3 the CPU gates were
1.754× median and 1.394× summed. Against ordinary 20/8 the median/summed
speedups were 1.010×/1.042× wall and 1.010×/1.043× CPU. The unchanged
ordinary 20/8 receiver and renderer are the comparison for attribution.
Both original recordings and archive snapshots were already in tmpfs.
The measured order was 0107 then 0016, with one candidate per recording
and previously verified control clocks. The earlier planned first-use
children ran in 0.594818 s and 8.037568 s wall respectively. Those separate
single runs supply context for the different admission modes. [0107 planned
first use](legacy-first-use-0107.md) · [0016 planned first use](legacy-first-use-0016.md)

## Issued work and verification

- **DS30-0107** admitted 27 of 29 issued visits, producing 54 receiver
  opportunities and 19 factors. The partial visit had 136,857 samples
  and the invalid zero-length visit had none. The 8 full and 19 short
  visits reproduced the exact signed native rows and graph proof. Both
  position and conditional RF arms were null, the through-exit solver
  stayed inactive, and no figures, position grid or path were emitted.
  One literal map covered 33,519,983 original compressed bytes and
  produced 14,872 map bytes plus 881 custody bytes.
- **DS30-0016** admitted 713 of 808 issued visits. Both positions and RF
  arms, 115 ordered owners and roles in each arm, the 179-point grid,
  path, exact title and all eight PNG bytes matched the ordinary 20/8
  publication. The c0 position was 37.8459892672°, −122.4897631356°
  with conditional RF RMS 134.021487 Hz. Fitted c returned
  37.8476459517°, −122.4967724341° with 133.739967 Hz. Earlier scoring
  places these at 0.490 km and 0.980 km from the operator reference,
  respectively. The five literal and eight exception maps covered
  991,734,597 original compressed bytes and produced 2,138,415 map bytes
  plus 7,902 custody bytes. [Prior position assessment](frame-portable-0016.md)

The worker authenticated the original payload and complete decoded
authority during ordinary acquisition. It built each map from those
samples, reopened it on the same authenticated encoded bytes and
verified the first 640,000-byte prefix before publication. The offline
scorer then reopened the durable custody and every map, reapplied the
external authenticated pins and compared bytes to separate earlier map
builders. No prior custody, map path or map bytes were supplied to a
candidate. Both children used verified-original authority mode. The
scorer initially applied the smaller custody-file byte bound to
exception maps. Correcting it to use each decoder's limit required only
offline readback. Both published candidate processes were preserved.

## Clock boundaries

The measured clocks cover child dispatch through exit, with authenticated
read, receiver, solver when eligible, figures, and durable map
publication. DS30-0107 spent 0.134 s in authenticated acquisition and
DS30-0016 spent 3.419 s. In-child map setup took 0.183 s in each
recording. Discovery and history planning built into acquisition took
1.3 ms and 25.9 ms. Serializing the maps and reopening them took 2.6 ms
and 56.0 ms together. Complete map bundle publication took 0.394 ms and
2.431 ms. These phases are covered by the measured child clocks.
DS30-0016 used the earlier portable producer locally for 19 bodies, with
one body prepared cold, and drew four ordinary orbit figures.

Controller admission before the children took 1.031 s wall / 1.022 s
CPU, mainly the study's tiny metadata checks and local archive custody
verification. Separate setup-only probes took 0.366 s wall / 0.364 s
child CPU and 0.372 s wall / 0.370 s child CPU and opened zero waveform
files. The through-exit clocks independently repay the runtime setup.
Already built native libraries were reused. The earlier orbit artifact
was built once for 4.320 s wall / 4.319 s CPU and is a separate reusable
cost. No original waveform conversion, staging pass or source RAID read
occurred here. [Earlier prepared-map and portable producer accounting](legacy-block-all-0016.md)

## Reproduction

Use the existing read-only bind mounts and shared Gauss lock for both
originals, then run `legacy_first_map_panel.py launch FRESH_TMPFS_ROOT`
and the offline `score` action. The frozen launched revision was
`8daf2f485f869b3e26addfd07f6628c761300347`. The work was pinned to CPU 2,
nice 15, best-effort I/O priority 7 and one numerical thread. Both native
library digests and command lines, original and causal input pins, full
child clocks and separate admission, complete scientific witnesses and
all map records are present in the archive. Sixteen component tests
passed, including partial and zero visits, absent prior custody,
corruption before publication, and an oversized exception-map readback
regression.

- [Frozen protocol](legacy-first-use-original-panel-protocol.md)
- [Machine receipt](measurements/legacy-first-use-original-panel.json.gz),
  uncompressed SHA-256
  `c4af0fb8f0795ce2fd46aa93953fbf4cc30c481cf44b12b99db745f0411005da`
