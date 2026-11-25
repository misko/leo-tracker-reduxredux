# Resident-source reuse of the scheduled DS30-0208 stage

The alternate byte reader opens only the 13 enrolled files in the exact detached first segment. It pins a directory descriptor, checks regular files and signed sizes, and requires the caller to own each file for a trustworthy Linux `mincore` census. It passively checks every enrolled extent before the first data call and then checks each at-most-1 MiB span immediately before `preadv2(RWF_NOWAIT)`. The installed Python build exposes `os.preadv` but rejects nonzero flags, so the reader calls the libc entry directly. A short read, cache miss, unsupported call, observed I/O charge, path or identity change, or hash mismatch ends the replay. There is no retry or blocking fallback. The reader holds the ordinary single compressed member buffer and reuses the small signed manifest and indexes in memory. It uses the scheduled files directly with zero additional persistent copy bytes. [Reader](directed_stage_cache_reader.py)

A separate cold-file probe on the same ext4 device returned `EAGAIN` while charging 131,072 read bytes and 256 input blocks, leaving 32 of 256 formerly absent pages resident. `POSIX_FADV_RANDOM` also incurred the charge. Pages can still be reclaimed between the passive check and the data call. The reader samples both thread I/O counters around every call, including errors. The first observed charge is a refusal, even when the returned byte count is zero. The refused call and all preceding returned bytes and I/O charges are kept in the receipt. Whole-process I/O is reported separately. These are observed counters for the measured intervals. A completed strict replay has a clean source receipt and all signed verification results. [Replay and receipt](directed_0208_reuse.py)

The installed manifest parser, typed index, compressed check, zstd stream, per-window check and complete decoded-member check remain active. The same signed ordered index hashes also constrain the original directed sweep. The adapter calls the frozen three-phase verifier and scorer. It requires the completed booked capture with the signed total and inventory, the generation-matched verified pair, the exact original unfiltered 20/8 packet and the installed packet and owner witness bound to both original calibration arms. Candidate Graph and proposal output seal before the installed prerequisite is checked. An incomplete waveform sweep gets no acceptance receipt. [Prepared entry](directed_0208_reuse.py) · [Frozen selection and cost scope](directed-second-enrollment-protocol.md)

On Gauss's detached NVMe ext4 filesystem (device `66311`), the released Python executable ran three disposable 1 MiB fixtures on CPU3. The syscall trace recorded one `preadv2` with `RWF_NOWAIT` for the warm file and no other `preadv` or `preadv2` calls. [Reproduction](directed_stage_cache_fixture.py) · [Measured receipt](measurements/directed-stage-cache-fixture.json)

| Initial cache | Pages before → after | NOWAIT calls | Outcome | Observed source read charge |
| --- | --- | ---: | --- | ---: |
| Cold | 0/256 → 0/256 | 0 | Refused before data call | 0 bytes, 0 blocks |
| Mixed | 128/256 → 128/256 | 0 | Refused before data call | 0 bytes, 0 blocks |
| Warm | 256/256 → 256/256 | 1 | Exact 1,048,576-byte read | 0 bytes, 0 blocks |

Twenty-seven fixture and adjacent tests passed. The tests reproduced stock decoded rows, rejected each signed integrity fault separately, and covered intervening eviction, short reads, unsupported reads and a first-call `EAGAIN` with 131,072 charged bytes and 256 blocks carried into the refusal. Scoring rejects a receipt carrying a read charge. No enrolled DS30-0208 source file was opened and no numerical trial ran. A future warm candidate remains eligible under the existing matched-pair, capture and lease conditions.

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

The external clocks include interpreter startup and exit for the proposal and replay processes separately. The internal receipts retain Graph and proposal cost, complete replay cost, native phase clocks, passive residency, call counters, byte returns and charges, and the original signed matches. Scoring is a third readout. The earlier DS30-0049 marginal verifier clock remains a separate measurement. A separate saved position comparison would use every actual interpolated accept and the ordinary charted control under its own admission.
