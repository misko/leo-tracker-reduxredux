# Expand development coverage without consuming another holdout

Use the first32 consecutive visits of each original64-visit `dev` block in
dataset/cases.json. Membership depends only on frozen metadata and source
counters, not signal outcomes. These original sessions were exposed in earlier
experiments; they are additional development coverage, not new independent
validation. Their rate/edge strata reverse those in the recent64-visit cohort:
2.5 MS/s lower edge and 5 MS/s upper edge. Original holdout entries are excluded.

Compare full current application and unchanged early_local_tracking candidate
with independently causal state, cold session starts, and rotating execution
order. Record full reference pair inventory for a later proposal diagnostic.
No rescue yet. Assess reference identity, extras and visit loss; unknown recorded
signals are never converted into constructed-negative ground truth.

Freeze all64 descriptors and source hashes before reading IQ. CPU0, numerical
threads=1,300-second total bound. Whole-call timing includes conversion and
confirmations but excludes initialization/IO/hash/serialization. Save per-visit
checkpoints and final rows before analysis. Preserve failures and partial runs.
No new RF collection, QNAP writes or production changes. Once coverage is known,
use a separate bounded proposal study; do not change policy during this replay.
