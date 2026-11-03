# DS9 host-timestamp sensitivity diagnostic

This bounded host diagnostic translates timestamps in copies of the retained
public DS9 candidate and graph-authority TSVs, then runs the unchanged native
tracking, pipeline and location components. It is evidence about this corpus;
it does not qualify a host-timed source, establish a safe timestamp threshold,
or change production code, contracts, fixtures or goldens.

The baseline contains 11,747 candidates, 3,563 public `source_group_id` values,
and reconstructs 64 tracks containing 3,372 selected points. The seven cases
are the baseline, common `+1`, `+10`, and `+50 ms` offsets, and bounded `1`,
`10`, and `50 ms` jitter. A common case translates every support interval by
`+A`. A jitter case sorts the public source-group IDs and gives even ranks
`-A` and odd ranks `+A`. Every candidate alternative in a source group gets
the same delta. The fixture exposes no visit ID, so these are source-group
jitters and cannot be claimed as exact per-visit jitters.

For every row, start, center and end move together in both TSVs. Support width,
moments, CFO and detector scores, candidate/source IDs, and row order remain
unchanged. Graph `session_start_utc_ns` remains fixed so the translated capture
times move relative to the retained orbit authority. Keeping the original IDs
is deliberate experimental control and makes the copies diagnostic inputs,
not newly attested persisted observations. Exact compressed copies and their
group ordering are retained in `input-copies/` and
`perturbation-manifest.json`.

## Results

| case | exact baseline track memberships | changed train-mask bits / compared | fixed-site RMSE absolute delta (Hz) |
|---|---:|---:|---:|
| common +1 ms | 64 / 64 | 1,616 / 3,372 | 34.8605, 22.7338 |
| common +10 ms | 64 / 64 | 1,670 / 3,372 | 27.1747, 12.2560 |
| common +50 ms | 64 / 64 | 1,630 / 3,372 | 3.59125, 2.11127 |
| jitter +/-1 ms | 49 / 64 | 1,256 / 2,650 shared-track bits | 26.2437, 8.96526 |
| jitter +/-10 ms | 39 / 64 | 888 / 1,850 shared-track bits | 49.7796, 17.0472 |
| jitter +/-50 ms | 21 / 64 | 446 / 947 shared-track bits | 56.7759, 30.0274 |

Every case still reconstructs 64 tracks and both fixed sites match all 64.
Common offsets preserve every candidate membership, alias and tracking fit
value. Nevertheless, each common offset changes all 64 support digests and
partition seeds because timestamps are part of the support authority. About
half of the train/holdout bits are consequently reselected. The fixed-site
score changes therefore combine orbital timestamp sensitivity with a distinct
deterministic partition reseeding effect. Their non-monotonic sizes must not be
read as a physical error curve.

Source-group jitter affects reconstruction itself: even the `+/-1 ms` case
replaces 15 of 64 exact candidate-membership tracks. On the 49 shared tracks,
the maximum rate change is 0.3743 Hz/s and maximum residual-RMS change is
1.2347 Hz. The `+/-50 ms` case retains only 21 exact memberships and reaches a
14.7653 Hz/s rate change and 139.852 Hz residual-RMS change. This rules out an
assumption that millisecond-scale independent group errors are harmless on
this recording. It does not establish 1 ms as a rejection threshold: only
three deterministic amplitudes and one sign pattern were tested, and
partition reseeding is coupled to the public pipeline identity.

The original 400-point Sacramento and Reno policies were also run for the
baseline, common `+50 ms`, and jitter `+/-50 ms`. All six searches consumed the
400-point budget and remained explicitly unconverged. Their grid incumbents
did not move: Sacramento stayed at `(-81.25, -81.25) km` and Reno at
`(343.75, 81.25) km`. Common-offset incumbent scores moved by 3.59125 and
2.11127 Hz; jittered scores moved by 56.7759 and 30.0274 Hz. Deferred cells
were baseline `90/175`, common `87/184`, and jitter `85/176` for
Sacramento/Reno. The baseline is the current native toolchain and retained
authority used by this diagnostic. These counts are comparator provenance,
not server goldens; in particular the Sacramento count is not substituted for
the earlier C7 reference result.

The complete matrix took 390.585 seconds under a 590-second internal deadline
and an external 600-second watchdog. All component builds and tests passed;
all retained command stderr files are empty. No hardware, RF, raw-IQ replay,
network service, reference implementation, saved winner list, or oracle
shortlist was used.

`result.json` contains the full comparisons and timings. `raw/` preserves each
tracking graph, pipeline graph, fixed-site result and six regional search
traces. `source-manifest.json`, `evidence-sha256.json`, `COMMANDS.txt`, and the
build logs bind the executable closure and reproduction procedure.
