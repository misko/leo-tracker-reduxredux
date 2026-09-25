# Adaptive v0.57 random active-dwell rollout for radio .20

## Intended result

Each adaptive scan on radio `192.168.1.20` remains a fixed-rate, dual-RX,
10 MS/s scan on the existing ten-minute schedule. Before the scan starts, the
host makes one uniform choice from `120`, `240`, and `360` ms. That value is the
scan's **active dwell floor** and is immutable for the scan.

Every channel begins inactive and receives exactly 120 ms visits. After the
firmware applies a valid ACTIVE result for a channel, later visits to that
channel use at least the selected active dwell. The initial v0.57 policy uses
exactly the selected value; describing it as a floor leaves room for a future,
separately versioned extension without weakening this release. An applied QUIET
result returns that channel to exactly 120 ms. UNKNOWN, dropped, rejected,
expired, duplicate, superseded, or late feedback does not change its state.

```text
                         applied ACTIVE
inactive: 120 ms  ─────────────────────────► active: selected 120/240/360 ms
       ▲                                               │
       └──────────────── applied QUIET ─────────────────┘
```

The active latch is distinct from the current scheduling-weight boost. Weight
may decay without clearing activity. This implements “already detected as
active” literally: only affirmative QUIET evidence clears the longer dwell.
The scan cadence, sample rate, channel edge selection, detector thresholds, and
target weighting policy do not become random as part of this change.

## Existing foundation and gaps

The earlier feature-103 wire protocol v3 already defines nearly this shape:
dual RX, 2.5 or 10 MS/s, an active base of 120/240/360 ms, exact per-visit
`valid_start`/`valid_end`, and 120 ms quiet probes. Its persisted reader,
variable-duration capture contracts, UI fields, and per-visit analysis have
also been prototyped in the `leo-adaptive-random-dwells` line. Reuse these
reviewed contracts rather than creating another incompatible representation.

Three corrections are required before production:

1. The current libiio issue-114 head replaced activity-dependent v3 with a
   scan-wide fixed-dwell v4. v0.57 must advertise and implement v3 alongside
   v4; neither protocol may silently fall back to the other.
2. The old v3 implementation tied activity to boost decay. v0.57 must retain
   the activity latch until applied QUIET feedback.
3. The production analysis enqueuer currently skips variable-dwell receipt V6.
   The variable-duration analyzer must be deployed before v0.57 recordings are
   admitted to production.

The current source worktrees contain unrelated and uncommitted work. Build the
release from clean, dedicated branches based on the exact deployed host and
v0.56 firmware revisions. Reference worktrees are numerical/design sources,
not runtime dependencies.

## Gate 1 — freeze the behavior and identities

Write an executable policy table covering every feedback result and channel
state. Treat feedback as state-changing only when the firmware has accepted it,
verified its session/generation/digest, matched it to one complete intact visit,
and emitted an APPLIED acknowledgement. Record the acknowledgement's first
affected visit so the capture can be replayed exactly.

Choose the active dwell once on the host before opening the scan session. Use
domain-separated SHA-256 rejection sampling over the radio serial and scan-slot
ordinal, matching the existing unbiased rate/edge selector. Persist all of:

- candidate set `(120, 240, 360)`;
- selected active dwell;
- selector version/domain and slot ordinal;
- setup seed, exact wire version, rate, edge, serial, and firmware identity.

The selection must be reproducible from recorded inputs while remaining uniform.
Do not use process-global PRNG state, modulo-biased selection, wall-clock calls
made after capture begins, or a random choice made independently by firmware.
The host sends the chosen value in the immutable setup; firmware attests every
actual interval in its visit records.

**Gate:** a one-page contract and test vectors agree across C firmware, Python
wire models, the live runner, importer, and UI terminology.

## Gate 2 — implement the v0.57 firmware contract

Start a clean libiio branch from the v0.56 deployed source and restore the exact
v3 command surface (`SCANCAPS3`, setup v3, visit v3) alongside the existing v1,
v2, and v4 behavior. Advertise only the qualified v3 geometry: dual RX CI16,
2.5 and 10 MS/s, quiet dwell 120 ms, and active dwell candidates
120/240/360 ms. A v3 request must fail closed if any capability differs.

In the policy engine:

- initialize every target `inactive`;
- choose 120 ms for an inactive target and the setup's active dwell for an
  active target;
- update the latch only while applying valid ACTIVE or QUIET feedback;
- keep boost/decay responsible only for selection probability;
- size visit ledgers and queues for the worst case of all 120 ms visits;
- prove revisit feasibility using the worst-case active dwell selected for the
  scan, even while all current targets are quiet;
- admit a terminal visit only when its complete selected dwell plus transition
  fits; never publish a shortened long dwell as complete;
- reserve, capture, account, and checksum IQ from the visit's authoritative
  duration, not the setup's quiet duration;
- retain exact dual-RX interleaving and counter continuity.

Keep wire v3 immutable. If any desired semantic cannot be represented without
changing a published field or acknowledgement meaning, introduce a new wire
version rather than redefining v3.

Build v0.57 from clean, immutable firmware and libiio commits. Give it a unique
firmware identity such as `v0.57-plutoplus-spf-adaptive-random-dwell-v1`; freeze
the final name before qualification. Seal source commits, toolchain identity,
DFU/FRM/FIT hashes, device-tree/layout identity, metadata ABI, and rollback
image in the candidate manifest.

**Component tests:** all three active choices; initial quiet behavior; ACTIVE
and QUIET transitions; repeated ACTIVE; UNKNOWN and every non-applied feedback
result; activity surviving weight decay; feedback races; deadline-forced visits;
terminal tails; counter overflow; queue pressure; cancellation/restoration;
dual-RX byte counts; deterministic replay; and compatibility tests proving v1,
v2, and v4 are unchanged.

**Gate:** the complete C suite, sanitizers, protocol golden vectors, and a
long deterministic policy simulation pass with no missed revisit deadline,
partial complete visit, or unexplained state transition.

## Gate 3 — update the host runner and durable evidence

Extend the v0.56 dual-RX live runner rather than creating a parallel capture
path. The production service remains pinned to `--sample-rate 10000000`. Before
each run it derives `active_dwell_ms`, requests wire v3 explicitly, and refuses
an endpoint that does not advertise the exact v3 capability. No fallback to
fixed 120 ms or fixed-dwell v4 is allowed after a v3 request.

Keep `dwell_ms` in the wire setup as the selected active dwell for compatibility
with the existing v3 contract, but use unambiguous names in operator evidence:
`quiet_dwell_ms=120` and `selected_active_dwell_ms`. Archive every visit's actual
duration and the APPLIED acknowledgement boundary that changed its target's
state. The summary must report visit and valid-IQ counts by channel, activity
state, and actual duration.

Update capacity calculations for the largest possible scan. At 10 MS/s and
dual RX, 360 ms visits are large; verify NVMe spool admission, maximum IIO block,
queue bytes, memory peak, transfer time, canonical expansion, RAID growth, and
analysis arrival rate. Preserve acquisition's current CPU/I/O priority and
allow the low-priority publisher to run concurrently without owning the radio
lock.

**Gate:** pure host tests reproduce all C vectors; archive round trips preserve
120/240/360 ms counters and bytes; restart and interruption leave the sealed
source recoverable and publication idempotent.

## Gate 4 — make the full analysis path variable-dwell aware

Integrate the existing receipt-V6 and event-V3 work into a clean production
release, including the radio `.20` identity and 10 MS/s importer support already
needed by fixed-dwell scans. Each visit's authoritative duration is
`valid_end_counter_exclusive - valid_start_counter`; no consumer may infer it
from a fixed setup value.

Deploy variable-duration analysis before enabling v0.57 capture:

- remove the queue's receipt-V6 skip only after its completion predicates
  understand V6;
- schedule 20 ms GLRT probes using each visit's actual span; with the current
  120 ms production stride, a 120/240/360 ms visit contributes 1/2/3 time
  positions per receiver;
- bind metrics and resumable checkpoints to the exact capture manifest and
  variable-dwell configuration;
- keep relative phase, tracking, Doppler, candidate association, and position
  timing on the recorded counters;
- show the scan-selected active dwell and each visit's actual duration in the
  API/UI;
- report unsupported scientific stages explicitly instead of marking the
  session complete from overview rendering alone.

Test mixed quiet/active sequences, all three selected values, both receivers,
sparse/missing visits, interrupted publication, analysis resume, input digest
changes, tracking handoff, UI pagination, and API artifact retrieval. Preserve
existing scientific goldens unless an explicit review approves a new fixture.

**Gate:** saved synthetic v3 archives and at least one existing read-only
variable-dwell corpus item complete metrics, overview, relative phase, tracking,
association, and position stages through the installed API/UI.

## Gate 5 — qualify the exact v0.57 bytes before LAN promotion

Qualification must exercise explicit 120, 240, and 360 ms active selections;
do not wait for random production slots to provide coverage. Begin with C/host
simulation and archive replay. Then qualify the exact candidate bytes through
the existing RAM/local persistent workflow on the authorized hardware, covering
boot, idle/TX-safe state, scan capability, bounded dual-RX captures, reboot and
cold return, failure recovery, and rollback to the preserved v0.56 image.

Any RF collection used for qualification requires explicit authorization at
execution time and a declared aggregate RF bound of at most 30 minutes. Use
short, deterministic cells for the three dwell choices rather than a long
campaign. The qualification report must distinguish transport/counter proof,
detector feedback proof, and scientific signal findings.

Only after exact-byte qualification should the guarded firmware policy gain a
new immutable LAN promotion profile, for example
`adaptive-v057-random-dwell-r20-persistent-promotion`. Bind it to:

- serial `1040005e0b100007100010000bf33a5d4d`;
- host `192.168.1.20`;
- the exact allowed v0.56 source firmware identity;
- the exact v0.57 target, hashes, metadata ABI, IIO layout and v3 capabilities;
- TX-disabled preflight and return state;
- the exact v0.56 rollback artifact.

**Gate:** the immutable promotion profile, qualification receipt, rollback
receipt, and independent artifact/hash review all pass. A locally useful
candidate is not automatically authorized for LAN flash.

## Gate 6 — update radio .20 to v0.57 over IP

Schedule a maintenance window between scan slots. Pause the adaptive timer,
drain the active capture, preserve sealed NVMe spools, and acquire the existing
serial-bound radio lock. Analysis may continue because it does not own the
radio. Read-only preflight must attest the literal private address, exact serial,
current v0.56 identity, TX-disabled state, updater, QSPI layout, enrolled SSH
key, and rollback material.

Run the guarded LAN tool in plan mode first using the new reviewed profile:

```bash
uv run pluto firmware flash-lan /absolute/path/to/qualified-v057-pluto.dfu \
  --serial 1040005e0b100007100010000bf33a5d4d \
  --host 192.168.1.20 \
  --profile adaptive-v057-random-dwell-r20-persistent-promotion \
  --ssh-known-hosts-file /private/1040005e0b100007100010000bf33a5d4d.lan-20.known_hosts
```

Review the generated source/target identities, DFU/FRM/FIT hashes, layout,
TX-safety checks, rollback target, and confirmation phrase. Then execute the
same immutable inputs with a private credential source and receipt directory:

```bash
uv run pluto firmware flash-lan /absolute/path/to/qualified-v057-pluto.dfu \
  --serial 1040005e0b100007100010000bf33a5d4d \
  --host 192.168.1.20 \
  --profile adaptive-v057-random-dwell-r20-persistent-promotion \
  --ssh-known-hosts-file /private/1040005e0b100007100010000bf33a5d4d.lan-20.known_hosts \
  --ssh-password-file /private/radio.password \
  --receipt-directory /private/v057-lan-flash-receipts \
  --return-timeout 420 \
  --execute \
  --confirm 'FLASH LAN 1040005e0b100007100010000bf33a5d4d 192.168.1.20'
```

The paths and profile name above are placeholders until qualification freezes
them; never substitute an unreviewed image. After updater dispatch, an ambiguous
return is not safely retryable. Perform read-only reconciliation first. On
return, require the exact serial, v0.57 version, boot identity, metadata ABI,
dual-RX layout, TX-safe state, and `SCANCAPS3` values. Archive the rotated SSH
host key and complete the guarded final QSPI/device-tree attestation.

**Gate:** `.20` returns as the exact v0.57 image with a complete schema-v2 LAN
flash receipt. No scan service starts merely because the host answers ping.

## Gate 7 — cut over capture and prove one complete vertical

Deploy the tested host capture/import/analysis release first, but keep the old
capture mode selected until the firmware attestation passes. Then point the
adaptive service at the immutable v0.57 runner, retaining fixed 10 MS/s and the
ten-minute schedule.

With explicit authorization for the bounded RF canary, run one short scan under
an external wall-clock stop. Verify its selected active dwell, 120 ms initial
visits, an ACTIVE transition if the detector supplies one, the acknowledgement
boundary, and every actual visit duration. A canary with no ACTIVE result is a
valid quiet-path test but does not qualify the active transition; use controlled
qualification evidence rather than collecting indefinitely for a live hit.

Trace the canary through sealed spool, verified RAID publication, queue,
metrics, overview, relative phase, tracking, association, position products,
and API/UI. Confirm the next scheduled scan independently chooses from all three
values and that restart cannot repeat a slot under a different choice.

Resume the timer only after the canary and one restart/reconciliation exercise
pass. Retain v0.56 firmware, the previous service drop-ins, and both host
releases as rollback targets.

## Acceptance checklist

- Selection is uniform over 120/240/360 ms, made once before each scan, and
  reproducible from sealed evidence.
- Every target starts at 120 ms; no inactive visit is longer or shorter.
- Applied ACTIVE changes only its target to the selected floor; applied QUIET
  returns only its target to 120 ms.
- Weight decay and non-applied feedback cannot clear or set activity.
- Every visit's counters, IQ bytes, archive metadata, importer, and analysis
  agree on its actual duration.
- Fixed 10 MS/s dual-RX capture on `.20` retains priority and the ten-minute
  schedule; publication and analysis do not hold the radio lock.
- Full analysis completes for variable-dwell receipts and is visible in the UI.
- The exact v0.57 bytes are qualified, flashed over the guarded LAN workflow,
  independently attested after return, and paired with a tested v0.56 rollback.

Rollback stops new capture first and preserves all spools, receipts, published
recordings, and analysis artifacts. Repoint the host service to the prior fixed
120 ms runner and use the reviewed guarded firmware rollback only after exact
serial/source-state attestation. Never delete or rewrite evidence to make a
failed canary appear clean.
