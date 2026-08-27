# Satellite Tracking UTC and Capture-Clock Timing Audit

Date: 2026-08-27 UTC

## Decision

The current opened-arc satellite-association result has **no software timezone
or fixed-hour conversion defect**. TLE epochs, TLE collection times, recording
timestamps, sample-support timestamps, and SGP4 propagation instants use one
POSIX timestamp convention with no local-zone conversion. Replaying the graph
and TLE epoch path under
`TZ=UTC`, `TZ=America/Los_Angeles`, and `TZ=Asia/Tokyo` produced identical
timestamps and graph digests.

The Pluto FPGA sample counters also provide a strong relative time axis. At
every graph support start, centre, and end, the absolute difference between the
nominal 2.5 MS/s clock and the refreshed per-refill counter fit, plus that
refill's declared uncertainty, is at most a conservative **1.184 ms** and
**0.751 ms**, respectively. The central rate estimates imply only about 19 and
22 microseconds of drift over the analyzed spans.

There is one important limit: these are bounds to the host's
`CLOCK_REALTIME`, not an independent calibration of that clock to true UTC.
Chronyd ran continuously with a selected NTP source and no clock step is
logged or visible, but the capture-time NTP offset and dispersion were not
retained. A constant host-to-UTC error therefore cannot be bounded
retrospectively to PNT accuracy.
This audit is green for publishing the present association/abstention result,
but absolute-time positioning remains gated.

| Question | Finding | Disposition |
|---|---|---|
| Local timezone interpreted as UTC? | No; all scientific values are POSIX nanoseconds and explicit UTC | **Pass** |
| Software shifts TLE or radio time by a timezone-sized interval? | No; parsing and graph construction are `TZ`-invariant | **Pass** |
| Counter gaps, refills lost, or a segmentation discontinuity? | No; all 572 inter-refill boundaries close exactly on both selected streams | **Pass** |
| Large sample-clock drift during either arc? | No; central estimates are order 1–2 ppm and tens of microseconds over each arc | **Pass for tracking** |
| Host clock stepped during capture? | No visible step; realtime-minus-monotonic changes by only a few microseconds | **Pass** |
| Host UTC offset known to PNT accuracy? | No archived NTP/PPS/PTP/GNSS offset or dispersion | **Not established** |
| Fitted catalogue `tau` usable as a receiver-clock correction? | No; it is deliberately an orbit/catalogue sensitivity state | **Forbidden inference** |

No RF was collected and no IQ was read for this audit. The QNAP corpus was
accessed read-only through manifests and compressed timing ledgers.

## Audited authority

The audit uses the exact streams registered by the frozen long-arc cohort and
development protocol:

- [post-fix-long-arc-research-cohort-v1.json](../config/analysis/post-fix-long-arc-research-cohort-v1.json)
- [satellite-pnt-long-arc-development-protocol-v1.json](../config/analysis/satellite-pnt-long-arc-development-protocol-v1.json)
- [machine-readable timing evidence](figures/2026_08_27_satellite_tracking_timing_audit/timing-audit-evidence.json)

| Arc | Manifest SHA-256 | Selected timeline SHA-256 | TLE SHA-256 |
|---|---|---|---|
| 9981 | `afaecccd1130c09d4604bdebc99ff8fbb4089c9dd031602b117312739be094e3` | `490409f4d483c5afda669f03c5a0f2def70f41159c52c747358adc9754f30ec8` | `ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee` |
| 150802 | `ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e` | `5bb681374533535e568ba0afca46a39dd4129bdfa33f85c0efccd6d0d17d5a8b` | `9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad` |

Both TLE snapshots contain 10,972 unique, checksum-valid 3LE records. Both
recordings use stream 1, radio serial
`10400056f695001322002d0010ad1719f2`, and an exact nominal sample period of
400 ns.

## UTC and timezone chain

The acquisition clock's `utc_ns()` is Python `time.time_ns()`, and session IDs
format that epoch with `tz=UTC`; see [clock.py](../src/leo/acquisition/clock.py)
and [service.py](../src/leo/acquisition/service.py). The current host is
`Etc/UTC`, stores the RTC as UTC (`LocalRTC=no`), and reports synchronized NTP.
Those host settings are corroborating evidence, while the explicit UTC code
path is what prevents a local-time conversion.

The session name denotes service startup, not sample zero. The observed
3.4–3.6 s difference is normal radio preparation time, not a timezone offset.

| Arc | Session-name instant | First sample estimate | Manifest first-sample interval | Analyzed support centres |
|---|---|---|---|---|
| 9981 | `2026-08-24T19:22:52Z` | `2026-08-24T19:22:55.412378614Z` | `19:22:55.411848873Z`–`19:22:55.412908355Z` | `19:22:55.422378414Z`–`19:23:25.397378414Z` |
| 150802 | `2026-08-25T15:08:02Z` | `2026-08-25T15:08:05.580127359Z` | `15:08:05.579614894Z`–`15:08:05.580639824Z` | `15:08:43.165078492Z`–`15:08:56.965091292Z` |

As a human sanity check, the first samples correspond to 12:22:55 PDT and
08:08:05 PDT. Nothing in the analysis reparses those display values; the
integer UTC nanoseconds remain unchanged.

The graph assigns support time as

\[
T_{\mathrm{graph}}(s)=\hat T_0+s\frac{10^9}{2{,}500{,}000}
=\hat T_0+400s\ \mathrm{ns},
\]

using the manifest's device-counter-anchored first-sample estimate. This is
implemented in
[long_arc_catalogue_adapter.py](../src/leo/analysis/research/long_arc_catalogue_adapter.py).
For 9981, a 20 ms CFO window is represented by the mean of its sample centres,
9.9998 ms after probe start. For 150802, the timestamp is the mean of the
complete selected symbol centres, 9.618–10.300 ms after each probe start.
Neither file-write time nor host read completion is used as sample time.

## TLE timing

| Arc | Snapshot collection timestamp | Lead to sample zero | Lead to earliest analyzed support boundary | Registered chronology result |
|---|---|---:|---:|---|
| 9981 | `2026-08-24T18:04:07.459418079Z` | 4,727.952960535 s | 4,727.952960535 s | Strictly before support |
| 150802 | `2026-08-25T14:02:12.658586719Z` | 3,952.921540640 s | 3,990.497017840 s | Strictly before support |

The collection timestamp is taken before the Space-Track login/query sequence,
so it is an attempt-start time rather than a receipt-completion time; see
[tle_collector.py](../src/leo/operations/tle_collector.py). The per-request
timeout is 30 s and the observed margins exceed 66 minutes, making late receipt
operationally implausible here. There is no explicit total-fetch-duration
receipt, however, so attempt start alone does not prove that all bytes existed
before support. A future collector receipt should persist both request start
and verified completion.

TLE element epochs are obtained from `Satrec` Julian epochs and propagation
instants are split directly from integer UTC nanoseconds into Julian day plus
fraction. All 10,972 elements in each snapshot predate collection. An
independent exact conversion of `YYDDD.dddddddd` differs from the `Satrec`
conversion by at most 256 ns, below the TLE epoch field's 864 microsecond
resolution. There is no century ambiguity: every audited year field is `26`.

## Counter continuity and sample-coordinate authority

At every refill boundary the audit verified

\[
g_i=C_i-(C_{i-1}+n_{i-1})=0.
\]

| Arc | Inclusive device-counter range | Refill count | Gaps / missing / overflows | Registered span |
|---|---:|---:|---|---:|
| 9981 | `660899093157..661049093156` | 573 | 0 / 0 / 0 | 75,000,000 samples; 30.000 s |
| 150802 | `838916038826..839066038825` | 573 | 0 / 0 / 0 | 34,562,500 samples; 13.825 s |

Each full recording contains one continuous 150,000,000-sample segment. For
all 573 refills, `device_sample_counter - first_counter` also equals the
persisted session sample start exactly. The refill-segmentation bug therefore
does not contaminate either registered long arc.

## Sample capture versus the local clock

The metadata path brackets FPGA counter reads with host monotonic timestamps,
fits counter-to-monotonic time, then brackets the conversion from monotonic to
host realtime. The persisted first-sample bounds are therefore the direct
answer for sample zero relative to the local host clock:

| Arc | First-sample counter-to-host half-width | Central sample-rate mismatch | Central accumulated drift | Conservative rate interval |
|---|---:|---:|---:|---:|
| 9981 | 0.529741 ms | about -0.64 ppm | about 19.1 microseconds / 30 s | -47.841 to +49.928 ppm |
| 150802 | 0.512465 ms | about -1.60 ppm | about 22.2 microseconds / 13.825 s | -100.354 to +98.805 ppm |

The central rate estimates come from a regression of persisted refill-start
monotonic time against FPGA counter: 2,499,998.407 and 2,499,995.992 samples/s.
Different endpoint and regression estimates show tens-of-microseconds fit
jitter, so “order 1–2 ppm” is defensible; the extra decimal places are not an
oscillator calibration. The wider conservative rate intervals add the two
endpoint uncertainty bounds and are the appropriate bounds when no stochastic
error model is assumed.

The current graph uses only sample zero plus the nominal sample rate. For every
observation support start, centre, and end in the registered span, the audit
locates the containing refill and reconstructs its point time as

\[
T_{\mathrm{fit}}(s)=T_i^{\mathrm{start}}
+(s-s_i)\frac{T_i^{\mathrm{end}}-T_i^{\mathrm{start}}}{n_i}.
\]

The conservative bound is

\[
B=\max_s\left(|T_{\mathrm{graph}}(s)-T_{\mathrm{fit}}(s)|+u_i\right),
\]

where `u_i` is that refill's declared `sample_time_uncertainty_ns`. This gives:

| Arc | Largest point-estimate difference | Conservative maximum absolute time-axis error relative to host clock |
|---|---:|---:|
| 9981 | 0.087 ms | **1.184 ms** |
| 150802 | 0.031 ms | **0.751 ms** |

These bounds include the persisted local mapping uncertainty over the selected
arcs. They do not include an unknown constant host-to-true-UTC offset.

### Buffer latency is not timestamp drift

The radio returns refills after samples have accumulated. Host read completion
occurs about 44–45 ms after the end of a typical 104.8576 ms refill, and the
first sample predates the first read by 95.946 ms (9981) and 202.642 ms
(150802). That latency is measured and expected. It is not used as sample time;
the hardware-counter mapping accounts for it while retaining the declared
residual timing uncertainty.

| Arc | Host read start minus block start, median | Maximum | Read completion after block end, median |
|---|---:|---:|---:|
| 9981 | 48.033 ms | 95.946 ms | about 44.49 ms |
| 150802 | 48.624 ms | 202.642 ms | about 45.08 ms |

## What can and cannot be bounded about absolute UTC

The persisted `CLOCK_REALTIME - CLOCK_MONOTONIC` mapping varies by at most
3.501 microseconds across the full 9981 capture and 0.324 microseconds across
the full 150802 capture. Its endpoint changes are only about 0.031 and 0.001
microseconds. This rules out a wall-clock step visible at the metadata
resolution during either capture.

Chronyd ran continuously across both captures with a selected authenticated
NTP source. No restart, source change, or clock step was logged or visible
during either arc. However, chrony tracking logs were disabled, and neither
PPS, active PTP, GNSS timing, nor a capture-time `chronyc tracking` receipt was
preserved. Consequently:

- fixed timezone/hour conversion errors inside the software path are ruled out,
  but an incorrectly set host clock is not;
- sample continuity and sample-to-host timing are bounded as above;
- a large within-capture host-clock step is ruled out; but
- a constant or slowly varying host offset from true UTC has **no defensible
  retrospective numeric bound**.

That last uncertainty is common to every sample in an arc. It should be a
separate, explicitly calibrated clock state in future PNT work, not silently
absorbed into a satellite orbit state.

## Parameters that are not clock measurements

The catalogue sensitivity `tau` in [-5,+5] s is explicitly declared
`tau_is_receiver_clock_correction=false` in the frozen protocol. Its broad or
nonzero optimum combines orbit-element age/error, along-track equivalence,
catalogue ambiguity, and radio-model sensitivity. The provisional -1 s region
for 9981 is therefore not evidence that the receiver clock was one second
wrong.

Likewise, LNB/receiver LO drift, satellite transmitter drift, CFO rate, and the
150802 frame-lattice rate enter radio frequency or symbol phase. They are
confounded physical observables, not independent UTC measurements.

The TEME-to-ECEF code currently approximates UT1 with UTC, with the documented
bound `|UT1-UTC| < 0.9 s`; see [frames.py](../src/leo/sky/frames.py). That is an
Earth-orientation modeling approximation, not a capture-clock correction. It
is acceptable for the present abstaining association analysis but should be
replaced by frozen IERS Earth-orientation parameters before precision PNT.

## Required next timing checkpoints

1. Carry the per-refill counter-to-realtime mapping and timestamp uncertainty
   into each support observation instead of reducing the entire stream to
   sample zero plus nominal 400 ns samples.
2. Persist capture-start and capture-end chrony source, offset, root dispersion,
   stratum, leap status, and synchronization state. Bind the acquisition source
   revision; both audited manifests currently have `producer.source_revision`
   unset.
3. For PNT qualification, use a hardware-disciplined PPS/PTP/GNSS reference and
   record its health and uncertainty in the immutable capture contract.
4. Freeze IERS EOP/DUT1 authority with the orbit inputs before assessing
   absolute position.
5. Keep catalogue `tau`, receiver clock, sample-rate error, LNB/LO drift, and
   satellite transmitter states separate in inference and reporting.

Until items 2–4 are complete, the present timing is suitable for relative CFO
tracking and conditional catalogue studies, but not for a claim that absolute
receiver UTC is known tightly enough for global positioning.
