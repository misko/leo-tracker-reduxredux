# Historical source preservation

`pre-tail-host704/test_direct_ci16_ingest.c` is the exact source named by the
initial normalized-ingest `host704/build-receipt.json`.  Its SHA-256 is
`7499eecb7d222c12039db24db1f3695c7548aacc3b76187d127ba05d34f08e77`,
matching the immutable receipt.

That cohort preceded the added non-frame tail test and was later superseded by
`host704-v2`; the raw-value v3 and Wave5 variants supersede its internal sample
semantics as well.  This directory restores publication reproducibility only.
It does not promote the earlier result, alter a receipt, or claim that the
preserved source is current.
