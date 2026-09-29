# Publication source-hash audit

`audit.py` catalogs every C and header file below `reports/`, then verifies that
every source SHA-256 named by every qualification `build-receipt.json` exists in
that catalog. Run it from any directory with:

```sh
python3 reports/2026_09_29_publication_source_audit/audit.py
```

The audit deliberately excludes the two adaptive-Q
`*-unlabeled-preinstrumentation` cohorts. Those runs predate the required
runtime scorer labels, were quarantined when that provenance problem was found,
and are explicitly ineligible as qualification evidence. Their receipts remain
listed in `excluded_receipts` so the exclusion is visible rather than silent.

The current `source-audit.json` result covers 731 qualification receipts and
44,796 source references, with zero missing source hashes. It separately lists
the two excluded receipts. In particular, the recovered measured Winograd V1
source with SHA-256
`4410d1d2da4c0a8457b6c46c982202fa2e884939b55487cb470a01c6c3ab015c`
is present in the catalog.
