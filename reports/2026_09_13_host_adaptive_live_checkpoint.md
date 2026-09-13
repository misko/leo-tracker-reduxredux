# Native host-adaptive deployment checkpoint

Release `f33bee7f892129496360508f477c7a343e6b1189` is staged and sealed,
but has not been selected for acquisition or API production.

The installed Python 3.14 runtime replayed saved native 10 MS/s session
`scan-hop-a942a0bce610f262`: all 2,387 visits completed with four workers,
120 ms probe stride and one BLAS thread per worker. Analysis took 407.435 s;
analysis plus three overview PNGs took 410.000 s, below the 600 s cadence.
Policy and counters were synthetic; IQ was from the saved physical RX0 capture.
This establishes analysis cost, not live adaptive scheduling or sensitivity.
Evidence: `/var/tmp/leo-host-native-cadence-20260913-v2/qualification.json`.

The first shadow RX0 canary failed before radio acquisition with `RadioBusyError`.
The shared global authority lease was held by PID 666359, a separate radio20
frequency-revisit qualification process. No lock was bypassed and that process
was not changed. The failed call is conservatively charged 8.002823 s, leaving
1,554.665735 s of the original RF allowance. No adaptive RF was collected by
this attempt. Evidence and the failed-attempt ledger remain at:

- `/srv/bulk/leo/qualification/host-adaptive-20260913/shadow-rx0/canary.json`
- `/var/tmp/leo-host-adaptive-rf-ledger-20260913.json`

Acquisition was stopped between scans at 19:58:43 UTC, then restarted at
20:04:23 UTC on its unchanged fixed profile. The 20:00 slot remained pending
because the same shared lease also prevented production capture; systemd retries.
The last completed slot was 19:50, session `scan-hop-5998a655aaddb867`,
2,386 visits and 95.4249% duty. Starting the service is not proof of resumed RF.

Next: verify lease availability and resumed production, review the failed
pre-acquisition attempt explicitly in the ledger, then run the four reserved
300 s qualification scans. Restore their full 1,200 s reservation plus the
300 s first scheduled verification when updating ledger bookkeeping: the failed
pre-acquisition attempt did not consume a successful canary. Stop on any live
gate failure. Only select the staged adaptive release after qualification passes.
Only radio `104000bac4950008230026001b440a003a` is authorized for this task.

The new UI reader places native host-adaptive captures under Adaptive Scan,
showing native 10 MS/s, physical RX and 2.5 MS/s decision processing. Historical
fixed-order captures remain under Persistent Hop + Scan. This UI is staged,
not yet the production reader.
