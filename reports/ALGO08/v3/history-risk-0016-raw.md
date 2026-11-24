# DS30-0016 complete raw history-risk benchmark

At the recorded readiness check, the private stage held **261,028,217 of 993,933,681 signed bytes**, with **732,905,464 bytes missing** and 18 of 28 files at their original extents. The missing bytes were all waveform data. The completed custody receipt was absent. The metadata-only check returned exit 2 and started zero workers. It read no waveform or catalogue bodies. This snapshot predates completion of any ongoing custody work. [Readiness receipt](measurements/history-risk-0016-readiness.json)

The enrolled pair uses the existing 808-visit recording, original operator offer, signed hardware cutoff and 46 original causal snapshots. Candidate first uses the pinned 20/8 ms held-history CLI and the earlier-orbit risk route with the standard named publication and cold catalogue preparation. Stock is the actual installed ALGO08v3 command and full 20 ms receiver. A complete stage licenses 991,734,597 compressed waveform bytes per worker, covering 13 members and 713 valid stereo visits. The pair never copies or conditions waveform data. Child wall and CPU clocks run through process exit. Candidate timeout is 75 seconds and the shared process wrapper gives the installed comparator 150 seconds. Partial or failed exits remain in the pre-score seal. [Frozen saved physical evidence](history-risk-weak-physical.md) · [Earlier original full-20 benchmark](raw-0016-best.md)

Readiness checks only direct directory entries and exact extents on the local tmpfs device. The launch separately authenticates the completed stage receipt and all 15 signed sidecars. It verifies the private read-only bind, all waveform and index pages at each process boundary, the local causal archive, the offer, active solver sources and receiver libraries. The driver records the running CLI and bootstrap hashes and checks that the optional packed reader, portable index and alternate renderers are disabled. Both CLIs pay their normal input verification and complete publication. Scoring compares both calibration arms and signed opportunities, audits the matched numerical grid and eight encoded and decoded PNGs for a fix, and retains explicit withholding. Fresh candidate owner rows are checked against the published digest. Archived ordered named rows are admitted only if the fresh named terminal and published owner digest agree. Accuracy and conditional and all-owner frequency fit are recorded separately. The saved candidate's time and earlier named full raw time carry their original, different time boundaries. [Runner](history_risk_0016_raw.py)

Eight focused tests passed. They exercise metadata-only inspection, missing and unsafe members, absent and mismatched custody, complete extent admission, the real candidate parser, optional-source compatibility and a candidate with empty stdout. Candidate receipts come from the authenticated bootstrap file, and the named launcher retains its stdout receipt. The ordinary command also passed dry parsing on the integrated CLI with the strict-reader flags present. The scorer reproduced the signed input, terminal, 1,426 opportunities, 109 owners per arm, complete grid and path, and all eight PNGs from the prior original named artifacts. No fresh physics or acquisition process ran during readiness qualification.

## Commands

From the corresponding frozen checkout, run the readiness check as the existing stage reader. Exit 0 means all exact extents and a local completion receipt are present. Exit 2 reports a blocked stage.

~~~sh
sudo -n -u leo python3 -B -m reports.ALGO08.v3.history_risk_0016_raw ready
~~~

Run the pair once after custody completes. The launch uses the existing private mount pattern and shared Gauss slot. The benchmark process output must be fresh, and the mount disappears with the private namespace.

~~~sh
sudo -n unshare --mount --propagation private /bin/bash -c '
set -eu
stage=/dev/shm/leo-v3-guarded-selective-0016-stage01
recording=/srv/bulk/leo/fast-scan-recordings/fast8-auto-20261113-112146-b04f5461-1-lower
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
mount --bind "$stage/$(basename "$recording")" "$recording"
mount -o remount,bind,ro "$recording"
exec flock -w 40 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  taskset -c 2 nice -n 15 ionice -c 2 -n 7 runuser -u leo -- env \
  PYTHONPATH="$PWD:$PWD/reports/ALGO08/v3:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$release/venv/bin/python" -Bm \
  reports.ALGO08.v3.history_risk_0016_raw launch /dev/shm/leo-v3-history-risk-0016-raw-result01
'
~~~

Score the sealed pair separately. The second command uses the checkout's read-only store API and can run outside the private mount namespace.

~~~sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 40 -x /tmp/leo-algo08v2-2x-bench/gauss.lock taskset -c 2 nice -n 15 ionice -c 2 -n 7 \
  sudo -n -u leo env PYTHONPATH="$PWD/src:$PWD:$PWD/reports/ALGO08/v3:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -Bm reports.ALGO08.v3.history_risk_0016_raw \
  score /dev/shm/leo-v3-history-risk-0016-raw-result01 \
  --output /dev/shm/leo-v3-history-risk-0016-raw-score01.json
~~~
