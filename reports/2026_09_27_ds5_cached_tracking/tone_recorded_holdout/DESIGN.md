# Recorded holdout qualification

Use all 128 original `dataset/cases.json` entries marked `holdout`, not the
unused suffix of new_data (which was designated development). These are two
separately selected recording sessions, 64 chronological visits per rate. Fix
membership and source hashes before loading IQ. No detector or rescue policy
changes: use the frozen native_tone_rescue candidate that passed constructed
validation. Once evaluated, these sessions are consumed holdout evidence.

Compare application, unchanged native tracking, and tone-removal rescue with
separate causal state, rotating execution order. Start each session cold. Use
existing 2us/8kHz pair association against full application inventory. Record
all extras and mismatches as reference-relative evidence, not physical false
alarms. Preserve all primary positives and report actual rescue calls.

Qualification bands are fixed before outcomes: at least 10x aggregate CPU
speedup per rate; at least 97% application-positive receiver identity retention
per rate; no lost application-positive visit identity; no additional unmatched
active receiver decisions introduced by rescue versus native baseline. These
are explicit research acceptance criteria for a small reference loss, not a
claim of a universal user-approved field error rate. Report also 1% and 5% bands,
latency percentiles/max and calls exceeding 120ms. Single-core real time is a
separate target and must not be claimed from 10x alone.

Run each rate once, sequentially, CPU0 and numerical threads=1, with a 300-second
bound per rate. Complete-call timing includes conversion, primary processing,
rescue acquisition/confirmation and controller work; exclude IO, initialization,
hashing and serialization. Preserve partial failures as receipts. Do not tune
on this holdout or rerun a scientific failure under a changed acceptance gate.
No RF collection, QNAP writes, production edits or deployment.
