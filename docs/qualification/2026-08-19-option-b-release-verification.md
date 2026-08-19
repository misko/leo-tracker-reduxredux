# ADR 0006 Option B release verification

- Date: 2026-08-19 05:39 UTC
- Qualified revision: `8fd5c936df69ab3fc79f9f2000966c401c6f9566`
- Run ID: `option-b-8fd5c93-verification`
- Verdict: **PASS**

The supported isolated release lane was rerun after accepting ADR 0006 Option
B and advancing the corpus declaration to v2. It used the dedicated
`leo_qualification` PostgreSQL database, temporary test schemas and bulk roots,
the protected local RETRO corpus read-only, and a temporary compiled web root.
It did not use the production catalog, restart a service, or access QNAP.

The sealed receipt is:

```text
/srv/bulk/leo/qualification/release/option-b-8fd5c93-verification/receipt.json
sha256 2a4ddf5c627e470a973990f08c1e8c3ed4631028e8ad244d4e078eca04a3c71b
```

Results:

| Gate | Result |
|---|---:|
| Protected RETRO/full Standard processing | 2 passed |
| Production TypeScript/Vite build | passed |
| Production Chromium E2E | 2 passed |

The receipt names the exact Option B commit and seals seven declared evidence
files. The dedicated database ended with only `public` and zero user relations.
A production-catalog query found no session containing the run ID or commit
identity. J1 remained non-executable unavailable historical evidence; this run
does not claim J1 parity, calibrated detection, or specificity.

This verifies the Option B changes against the protected scientific and browser
lane. It is not the final deployment receipt: the lane must be repeated against
the exact immutable release revision selected after terminal soak acceptance.
