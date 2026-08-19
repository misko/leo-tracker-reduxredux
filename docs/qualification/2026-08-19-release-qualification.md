# Protected corpus and Chromium release qualification

- Date: 2026-08-19 04:32 UTC
- Qualified revision: `5357e0138c2cf203351b707e5ddae845139d7661`
- Run ID: `release-20260819-5357e01-verified`
- Verdict: **PASS**

The supported `leo-release-qualify` command ran at nice 15 and idle I/O
priority. It used the dedicated `leo_qualification` PostgreSQL database, unique
test schemas, pytest/browser-owned temporary bulk roots, the held local corpus
read-only at `/srv/bulk/leo/test-corpus`, and a temporary compiled web root. It
did not start, stop, restart, or enable any service or timer and did not access
`/mnt/qnap01`.

The sealed receipt is:

```text
/srv/bulk/leo/qualification/release/release-20260819-5357e01-verified/receipt.json
sha256 103ba7a4550b541d8539e1ddb8cb14cd8cba544096778fa391a55df94d221d07
```

All seven receipt-declared evidence digests were independently checked with
`sha256sum -c`. The definition digest was
`29a4af40f76b9bb2d684d3ad4d4f990da590986f4dc021c86dd5a5f81dafb667`.
Every evidence file is mode `0440`; the run and its directories are mode
`0550`.

## Results

| Gate | Result | Duration |
| --- | --- | ---: |
| Protected real-IQ detector and full Standard processing | 2 passed, 251 deselected | 9.107 s |
| Production TypeScript/Vite build | passed; compiled asset inventory sealed | 1.911 s |
| Production Chromium E2E | 2 passed | 17.774 s |

The JUnit evidence digest is
`b014b9510d293905f61d6ef79aa7cc6f9b16b05b2354f70d6bb28381ae88f444`.
The exact compiled-web inventory digest is
`11516392e29ca1fdd70a5b12b228188a0ad63ffa62d2c1ec1e87abd515251a08`.
The final dedicated-database inspection found only `public` and zero user
relations. Thus all unique processing and browser schemas were removed.

During the 46-second production-catalog observation window, production gained
exactly one session and one run. Both were the ongoing acquisition soak:
`production-24h-20260819-01-trial-00000036` and its
`capture-7f949a73127b4f63ac0253cad7606ac5` analysis run. No qualification ID was
written to the production catalog. Acquisition, worker 01, and API remained
active with `NRestarts=0`. The release-qualification timer remained absent and
inactive.

After the sealed run, the portable repository gates were repeated against the
dedicated qualification database: Ruff check and format, mypy across 98 source
files, 251 non-real-corpus tests, lock validation, Vitest (2 tests), and the Vite
production build all passed. The lane itself supplies the two protected-corpus
tests and two production Chromium tests.

## Rejected precursor evidence and remediation

The preserved precursor run
`release-20260819-a572c89-first` passed its scientific and Chromium assertions,
but an independent post-run check found one browser test schema left in the
dedicated database. It is not the accepted operational proof. Only that
generated qualification schema was dropped; it was recoverable by rerunning the
test and contained no production data.

Revision `5357e01` added graceful Playwright server shutdown and an independent
public-only database pre/postcondition. A recognized test-schema leak now fails
the lane, is removed from the qualification database, and is recorded in the
sealed receipt. Unrelated schemas are never removed automatically. The verified
run above exercised this corrected path and left no schema behind.
