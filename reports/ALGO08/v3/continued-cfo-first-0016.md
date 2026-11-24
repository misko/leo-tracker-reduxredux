# Guarded selective CFO on the first physical DS30-0016 member

On this 64-visit member, the guarded 20/12 ms receiver and its held-cycle route finished through sealed detections and process exit in **0.642–0.647 s**. The named ALGO08v3 20 ms receiver took **1.227–1.260 s** in the same reversed-order pairs. Authenticated acquisition, the matched boundary inside the two processes, improved from **0.434–0.443 s to 0.286–0.290 s**. These clocks end before a position solve or any figure generation. The whole-process clock also includes the two receiver wrappers’ different source, import and initialization work.

| Order | Named wall / CPU through exit, s | Guarded wall / CPU through exit, s | Named / guarded acquisition wall, s | Named / guarded primary native CPU, s |
| --- | ---: | ---: | ---: | ---: |
| Named then guarded | 1.227 / 1.218 | 0.647 / 0.645 | 0.434 / 0.290 | 0.290 / 0.139 |
| Guarded then named | 1.260 / 1.259 | 0.642 / 0.640 | 0.443 / 0.286 | 0.296 / 0.137 |

Both arms read the same complete signed first member and index on an existing tmpfs stage. All 19,222 payload and index pages were resident before and after all four children. The two admitted files account for 78,554,951 compressed bytes, 102,400,000 decoded bytes and 173,091 index bytes. The first named child recorded 15 process-wide major faults and 1,752 input blocks despite the source residency checks. Its exact fault sources are unassigned. The other three children recorded no major faults or input blocks. The volume and source set were fixed. No other original waveform data was read or copied.

The original timeline admitted 58 stereo visits and rejected six. Named ran 116 full-lane measurements and yielded 12 factors. Guarded ran 16 full and 100 short lanes and yielded 45 factors, with 11 shared occupied lanes and nine strict signed rank-zero counterparts. Named reproduced all 116 of its admitted probe rows and all exclusions from its authentic complete recording. Live guarded continuation paid for seven of 34 short positives, amended six and needed one exact tail retry. Tail CPU was 4.97–5.00 ms and the final held-cycle replay cost 2.41–2.42 ms. Both orders produced identical protected output for each receiver under the shared prefix authority. The prefix and full 808-visit recording have different inventory and authority digests.

The guarded original, paid-mask acquisition and final selected rows agreed with their frozen complete-recording prefix counterparts within the existing guarded tolerances. The original signed CFOs were exact. The final maximum signed CFO difference was **5.24 × 10⁻¹⁰ Hz**, and the maximum margin difference was **1.89 × 10⁻¹³**. Rank, sample timing, membership, signed counters and RF were exact. The archive’s all-paid fixed-epoch prefix differed at 14 deliberately skipped CFO edits by up to 169.865 Hz. The signed observation record is materially unchanged against saved continuation, so the preregistered hybrid-fit condition was false.

| Held evidence | Complete cycles per receiver | Incomplete cycles per receiver | History minus unfiltered score by receiver, nats | EOF choice |
| --- | ---: | ---: | ---: | --- |
| Live 64 issued | 6 / 6 | 2 / 2 | −9.896 / −2.591 | Unfiltered |
| Saved 808 issued | 85 / 85 | 8 / 8 | −15.273 / −8.948 | Unfiltered |

The held-cycle reconstruction used the original pre-refinement factors in both cases. Both decisions kept all positives and retained guarded revisions only where live continuation had paid. The prefix kept 45 factors. The saved complete result kept 475 and paid 308 of 401 short-positive tail calls. This first-member test verifies the physical measurements underlying part of that saved projection and does not time the complete recording or establish a position result. [Complete saved DS30-0016 ablation](continued-cfo.md)

## Reproduction

Timed source `128897bcd`. The compact [receipt](measurements/continued-cfo-first-0016.json.gz) records the authenticated bounded input, both pair orders, signed rows, final verifier, and the initial failed attempt. The initial named traversal used the same one-member scope. Its candidate partner stopped before reading the waveform when the fresh native import guard detected an early research-wrapper import. That pair was discarded. The verifier also corrected its initial conflation of process-wide faults with per-file residency using the frozen file-level checks. Thirteen focused component tests passed after the correction.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
output=/dev/shm/leo-v3-continued-first-0016-reproduction
run_locked() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env TMPDIR=/dev/shm \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$PYTHONPATH" \
    "$release/venv/bin/python" -Bsm "$@"
}
PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD"
run_locked reports.ALGO08.v3.continued_cfo_first_0016 run "$output"
PYTHONPATH="$PWD/src:$PYTHONPATH"
run_locked reports.ALGO08.v3.continued_cfo_first_0016_score "$output" "$output/score.json"
```
