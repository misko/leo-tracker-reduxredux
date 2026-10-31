## DS27 acquisition inventory

DS27 contains **28 new acquisitions: 15 fast scans and 13 adaptive recordings**, all recorded at 10 Msps. Membership includes every discovered whole acquisition whose recorded start falls in the half-open interval **2026-10-30 14:42:46.099491067 UTC through 2026-10-31 14:34:49.391893560 UTC**. The lower boundary is DS26's frozen cutoff; the upper boundary was fixed once before the inventory census.

The inventory applies no channel, readiness, completeness, signal-quality, or position-error filter. It retains 27 complete acquisitions and one incomplete fast acquisition, DS27-0001. Duplicate physical copies are reconciled by their recorded content identity. No DS26 content identity overlaps DS27. The metadata describe 129,037 windows and 328,733,990,306 compressed bytes; IQ payloads were neither read nor rehashed.

ALGO04 evaluation covers the **15 fast scans**, retaining unavailable cases in its denominator. The 13 adaptive recordings remain part of DS27 but are inventory-only in this comparison. At the separately frozen public-input availability snapshot, 14 fast scans had an existing public GLRT input and 13 had a verified completed ALGO02 job. DS27-0006 had a public GLRT input and a failed ALGO02 job; DS27-0001 had no existing public GLRT input. All 13 adaptive recordings had existing public adaptive-analysis metadata. These are input-availability facts, not ALGO04 accuracy or recovery results.

The census used root privileges only to reconcile historical filesystem permissions and read metadata. It reported zero discovery, permission, or integrity errors. The inventory is a non-atomic metadata snapshot: source receipts were rechecked before sealing, and the public-input availability window is recorded separately in provenance. No GPS reference, new RF collection, IQ reprocessing, or production change was used to define membership.

[Full frozen manifest](manifest.json.gz) · [Compact acquisition table](inventory.csv) · [Provenance and exact timestamps](provenance.json) · [Artifact hashes](artifact-manifest.json)
