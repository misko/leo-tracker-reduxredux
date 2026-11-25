# Cache-only reuse of the scheduled DS30-0208 stage

The alternate byte reader opens only the 13 enrolled files in the exact detached first segment. It pins a directory descriptor, checks regular files and signed sizes, and reads at most 1 MiB per `preadv(RWF_NOWAIT)` call. A short read, cache miss, unsupported flag, unexpected input-block count, path/identity change or hash mismatch ends the replay. The reader has no blocking read path. It holds the ordinary single compressed member buffer and reuses only the small signed manifest and indexes in memory. The already scheduled files serve directly, with zero additional persistent copy bytes. [Reader](directed_stage_cache_reader.py)

The installed manifest parser, typed index, compressed check, zstd stream, per-window check and complete decoded-member check remain active. The same signed ordered index hashes also constrain the original directed sweep. The adapter calls the frozen three-phase verifier and scorer. It requires the completed booked capture with the signed total and inventory, the generation-matched verified pair, the exact original unfiltered 20/8 packet and the installed packet and owner witness bound to both original calibration arms. Candidate Graph and proposal output seal before the installed prerequisite is checked. An incomplete waveform sweep gets no acceptance receipt. [Prepared entry](directed_0208_reuse.py) · [Frozen selection and cost scope](directed-second-enrollment-protocol.md)

Twenty-two fixture and adjacent tests passed. They reproduced stock decoded rows, separately rejected altered encoded data, indexes and decoded hashes, and exercised missing windows, short reads, `EAGAIN`, unsupported reads, physical-block accounting and changed paths. The tests supplied a deterministic synthetic read backend. Capability and timing on the actual DS30-0208 NVMe stage remain unmeasured. This work opened no real source bodies and ran no numerical trial.

## Prepared commands for a separately authorized trial

Use the exact sealed `cache-capture-result.json` SHA-256 from the already scheduled service. The first command checks the captured authority and freezes the full candidate-only Graph and proposals. For the second command, supply a newly observed official `deferred_storage_busy` JSON event produced by the existing metadata watcher and the live driver PID. The runner rechecks it after taking the original exclusive nonblocking lock. Use a fresh private output path and keep all actual clocks, including a timeout. The third command scores the sealed results after the replay has exited.

```sh
set -eu
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
result=/dev/shm/leo-v3-directed-0208-held01
module=reports.ALGO08.v3.directed_0208_reuse
: "${capture_pin:?sealed completed scheduled cache capture SHA-256}"

low_priority() {
  cpu=$1
  shift
  sudo -n -u leo -- env PYTHONPATH="$release/src" OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    taskset -c "$cpu" nice -n15 ionice -c3 "$@"
}
clock_format='wall=%e user=%U sys=%S input_blocks=%I major_faults=%F rss_kib=%M exit=%x'
plan_pin=$(low_priority 3 /usr/bin/time -f "$clock_format" -o "$result.proposal.time" \
  "$release/venv/bin/python" -B -m "$module" prepare "$result" --capture-pin "$capture_pin")

: "${event:?fresh official deferral JSON}" "${driver_pid:?live frozen controller PID}"
waveform_pin=$(low_priority 2 /usr/bin/time -f "$clock_format" -o "$result/replay.time" \
  /usr/bin/timeout --signal=KILL 12s "$release/venv/bin/python" -B -m "$module" replay "$result" \
  --capture-pin "$capture_pin" --plan-pin "$plan_pin" --event "$event" --pid "$driver_pid")

low_priority 3 "$release/venv/bin/python" -B -m "$module" score "$result" \
  --capture-pin "$capture_pin" --plan-pin "$plan_pin" --waveform-pin "$waveform_pin"
```

The external clocks include interpreter startup and exit for the proposal and replay processes separately. The internal receipts retain Graph and proposal cost, complete replay cost, native phase clocks, read counts, returned bytes and the original signed matches. Scoring is a third readout. The earlier DS30-0049 marginal verifier clock is not substituted for these new costs. A separate saved position comparison would use every actual interpolated accept and the ordinary charted control under its own admission.
