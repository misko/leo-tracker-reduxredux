# Native adaptive history and web publication

Implemented the explicit V2 adaptive history/detail API and native analysis
presentation. Existing V1 routes retain their dual-RX contract and exclude native
captures. The UI can read both generations and falls back to V1 on older servers.
Native capture views show the physical RX, 10 MS/s recording, 2.5 MS/s host
decisions, delivery health, unknown results, source freshness and actual policy
choices separately. They do not request the legacy on-radio detector product.

The tracking reader now binds the actual native visit analysis; refinement
already accepts the native geometry. Both physical receivers have component
tests. These changes do not collect RF or change the production release.

Validation on 2026-09-13:

- 40 focused storage/API/science-reader tests passed in 9.04 seconds.
- Mypy passed for the five changed Python modules.
- All 166 web tests passed; TypeScript and Vite production build passed.
- Chromium loaded the generated production assets against synthetic captures
  published by the real storage/analysis/presentation code, for RX0 and RX1.
  All three PNGs decoded at 2480×1040, 2480×1152 and 2480×1840, with no page
  errors. Synthetic optional tracking/refinement products were explicitly absent.
  Evidence is in `/var/tmp/leo-host-web-20260913` (not RF qualification).

The existing fixed production scanner remains active. Its 19:10 UTC scan
completed with 2,386 visits and 954,384 ppm valid duty. Scheduler admission,
runtime packaging, representative saved-data throughput and the reserved live
canaries still precede adaptive cutover. The RF qualification ledger is unchanged.
