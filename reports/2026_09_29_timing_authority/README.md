# Capture timing evidence does not explain fitted time offsets by itself

**All 72 evaluation captures have reproducible device-counter-to-host-time
brackets, but 59 fitted recording-time offsets lie outside those brackets.**
This is a distinction between measured capture timing and phenomenological model
timing. It does not prove host UTC error or identify a physical satellite-clock
offset. Do not impose the host brackets as absolute UTC bounds without independent
host-clock discipline evidence.

| Dataset | Timing present / qualified | Median bracket width | Median realtime–monotonic spread | Fitted offsets outside bracket | Maximum distance outside |
|---|---:|---:|---:|---:|---:|
| DS7 | 24 / 24 | 364.09 ms | 0.689 µs | 19 / 24 | 1.047 s |
| DS8 | 24 / 24 | 364.23 ms | 0.590 µs | 19 / 24 | 1.918 s |
| DS9 | 24 / 24 | 363.44 ms | 0.538 µs | 21 / 24 | 2.166 s |
| Total | 72 / 72 | 364.05 ms | 0.593 µs | 59 / 72 | 2.166 s |

The full bracket range is 362.10–372.36 ms, approximately ±182 ms around the
midpoint. The largest sampled realtime-minus-monotonic spread is 4.183 µs.
These figures measure different things: begin-call latency brackets the first
sample, while clock-offset spread checks host clock consistency at three sampled
instants. Neither establishes absolute UTC accuracy or excludes an unsampled
transient. Qualification allows up to two seconds; it is a gate, not a measured
two-second standard deviation or proof of precision timing.

## What is independently evidenced

The persisted `host-bracketed-device-counter-utc-v1` authority stores host
realtime and monotonic readings immediately before and after `begin_session`,
and at terminal receipt. The installed contract states that sampling starts
before the begin call returns. The recorded first device counter anchors sample
times to that first-sample bracket using nominal sample rate.

This audit independently reconstructs the three realtime-minus-monotonic offsets,
their minimum/maximum spread, earliest/latest first-sample bounds, midpoint and
qualification. All 72 agree exactly with persisted fields. Every numerical
observation export uses that same midpoint as its start time. All terminal first
counters agree with the timing authority; terminal counter difference divided by
nominal rate is exactly 300 seconds for every scan. That last identity is not an
independent sample-clock calibration or proof of gapless collection.

No capture-level NTP/GNSS/PPS offset estimate, accuracy uncertainty or reference
clock identity is present in the timing authority inspected here. Its small
realtime-minus-monotonic spread does not establish agreement with UTC: a constant
host clock offset is invisible to this comparison. Current host synchronization
would not retroactively certify these historical captures. This report does not
claim an exhaustive search of all external system journals or equipment records.

## Comparison with fitted timing

Use unchanged q020 fitted positions and recording times from the nine eight-scan
target panels. A fitted `tau` shifts satellite-state evaluation relative to
observation UTC; it can absorb position, orbital, signal-processing or association
mismatch. It is not automatically a hardware latency estimate. The outside
counts compare those numerical values to the independent host brackets and do
not refit or score geography.

After observing the discrepancy, a separate **posthoc algebraic check** asked
whether one constant host UTC bias could make all existing fitted offsets
consistent with the brackets. For each scan, that hypothetical bias must belong
to `[tau - upper_bracket_offset, tau - lower_bracket_offset]`. Intersect the
intervals; all nine individual eight-scan panels have empty intersections.

| Eight-scan panel | Gap between incompatible common-bias intervals |
|---|---:|
| DS7 early | 1.218 s |
| DS7 middle | 0.996 s |
| DS7 late | 0.807 s |
| DS8 early | 0.898 s |
| DS8 middle | 2.152 s |
| DS8 late | 2.046 s |
| DS9 early | 1.533 s |
| DS9 middle | 2.118 s |
| DS9 late | 3.014 s |

Thus one constant bias cannot explain these *fixed fitted values* as physical
capture timing under the bracket model. This is not a new fit with a shared bias,
does not establish that the real host bias was constant, and does not prove the
bracket model plus a different geographic solution would fail.

## Verification and reproduction

The primary [protocol](PROTOCOL.md) preceded metadata execution. Use the public
`AdaptiveHopIqStore(read_only=True).inspect` port for every target recording;
manifest digests match both observation exports and the original plan. No storage
paths are constructed to bypass that port and no IQ is read. `metadata.json`
retains full timing authority, terminal counters, source bindings and installed
reader/contract digests. `results.json` binds that metadata and the independent
audit implementation and retains all 72 results plus every panel summary.

Two tests pass: bracket/spread reconstruction with corrupted-field rejection,
and explicit missing-authority handling. Ruff lint and formatting pass. Metadata
export completed within the 120-second cap. No collection, clock changes,
production edit, timing prior or geographic fit occurred.

```bash
.venv/bin/python -m unittest discover -s reports/2026_09_29_timing_authority -p 'test_*.py'
sudo -n timeout 120 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_timing_authority/export.py > reports/2026_09_29_timing_authority/metadata.json
.venv/bin/python reports/2026_09_29_timing_authority/audit.py
```

## Next decision

Treat physical capture-time uncertainty separately from model mismatch. A useful
next sensitivity model could combine the measured per-record host brackets with
an explicitly assumed shared UTC bias, retaining the free-timing baseline and
testing all panels. It must be labeled an assumption-dependent model, not a
calibrated prior, unless historical host discipline evidence is recovered.
The current result rules out interpreting the existing fitted offsets as measured
receiver latency. It does not yet improve localization; reliable short-window
sub-km accuracy remains unresolved.
